# Copyright (C) 2009-2017, Ecole Polytechnique Federale de Lausanne (EPFL) and
# Hospital Center and University of Lausanne (UNIL-CHUV), Switzerland
# All rights reserved.
#
#  This software is distributed under the open-source license Modified BSD.

""" CMP Stage for building connectivity matrices and resulting CFF file
"""

# Global imports
from traits.api import *
import glob
import os
import pickle
import gzip
import nibabel as nib
import numpy as np
import scipy.io as sio
import networkx as nx

# Nipype imports
import nipype.pipeline.engine as pe
from nipype.interfaces.base import BaseInterface, BaseInterfaceInputSpec,\
    traits, File, TraitedSpec, InputMultiPath, OutputMultiPath
from nipype.utils.filemanip import split_filename

# Own imports
from cmtklib.parcellation import get_parcellation
import cmtklib as cmtk
# import nipype.interfaces.cmtk as cmtk
from cmp.stages.common import Stage

class ConnectomeConfig(HasTraits):
    apply_scrubbing = Bool(False)
    FD_thr = Float(0.2)
    DVARS_thr = Float(4.0)
    output_types = List(['gPickle','mat','cff','graphml'])

    subject = Str()

class rsfmri_conmat_InputSpec(BaseInterfaceInputSpec):
    func_file = File(exists=True, mandatory=True, desc="fMRI volume")
    roi_volumes = InputMultiPath(File(exists=True), desc='ROI volumes registered to functional space')
    roi_graphmls = InputMultiPath(File(exists=True), desc='GraphML description file for ROI volumes (used only if parcellation_scheme == Lausanne2018)')
    parcellation_scheme = traits.Enum('Lausanne2008',['Lausanne2008','Lausanne2018','NativeFreesurfer','Custom'], usedefault=True)
    atlas_info = Dict(mandatory = False,desc="custom atlas information")
    apply_scrubbing = Bool(False)
    FD = File(exists=True)
    FD_th = Float()
    DVARS = File(exists=True)
    DVARS_th = Float()
    output_types = traits.List(Str, desc='Output types of the connectivity matrices')

class rsfmri_conmat_OutputSpec(TraitedSpec):
    avg_timeseries = OutputMultiPath(File(exists=True), desc="ROI average timeseries")
    scrubbed_idx = File(exists=True)
    connectivity_matrices = OutputMultiPath(File(exists=True))

class rsfmri_conmat(BaseInterface):
    input_spec = rsfmri_conmat_InputSpec
    output_spec = rsfmri_conmat_OutputSpec

    def _run_interface(self,runtime):
        """ compute the average signal for each GM ROI.
        """
        print("Compute average rs-fMRI signal for each cortical ROI")
        print("====================================================")

        fdata = nib.load( self.inputs.func_file ).get_data()

        tp = fdata.shape[3]

        # OLD
        # if self.inputs.parcellation_scheme != "Custom":
        #     resolutions = get_parcellation(self.inputs.parcellation_scheme)
        # else:
        #     resolutions = self.inputs.atlas_info

        # NEW
        print('Parcellation_scheme : %s' % self.inputs.parcellation_scheme)

        if self.inputs.parcellation_scheme != "Custom":
            if self.inputs.parcellation_scheme != "Lausanne2018":
                print "get resolutions from parcellation_scheme"
                resolutions = get_parcellation(self.inputs.parcellation_scheme)
            else:
                resolutions = get_parcellation(self.inputs.parcellation_scheme)
                for parkey, parval in resolutions.items():
                    for vol, graphml in zip(self.inputs.roi_volumes,self.inputs.roi_graphmls):
                        print parkey
                        if parkey in vol:
                            roi_fname = vol
                            print roi_fname
                        if parkey in graphml:
                            roi_graphml_fname = graphml
                            print roi_graphml_fname
                    #roi_fname = roi_volumes[r]
                    #r += 1
                    roi       = nib.load(roi_fname)
                    roiData   = roi.get_data()
                    resolutions[parkey]['number_of_regions'] = roiData.max()
                    resolutions[parkey]['node_information_graphml'] = os.path.abspath(roi_graphml_fname)

                del roi, roiData
                print("##################################################")
                print("Atlas info (Lausanne2018) :")
                print(resolutions)
                print("##################################################")
        else:
            print("get resolutions from atlas_info: ")
            resolutions = self.inputs.atlas_info
            print(resolutions)

        index = np.linspace(0,tp-1,tp).astype('int')

        # if self.inputs.apply_scrubbing:
        #     # load scrubbing FD and DVARS series
        #     FD = np.load( self.inputs.FD )
        #     DVARS = np.load( self.inputs.DVARS )
        #     # evaluate scrubbing mask
        #     FD_th = self.inputs.FD_th
        #     DVARS_th = self.inputs.DVARS_th
        #     FD_mask = np.array(np.nonzero(FD < FD_th))[0,:]
        #     DVARS_mask = np.array(np.nonzero(DVARS < DVARS_th))[0,:]
        #     index = np.sort(np.unique(np.concatenate((FD_mask,DVARS_mask)))) + 1
        #     index = np.concatenate(([0],index))
        #     log_scrubbing = "DISCARDED time points after scrubbing: " + str(FD.shape[0]-index.shape[0]+1) + " over " + str(FD.shape[0]+1)
        #     print(log_scrubbing)
        #     np.save( os.path.abspath( 'tp_after_scrubbing.npy'), index )
        #     sio.savemat( os.path.abspath('tp_after_scrubbing.mat'), {'index':index} )
        # else:
        #     index = np.linspace(0,tp-1,tp).astype('int')

        # loop throughout all the resolutions ('scale33', ..., 'scale500')
        for parkey, parval in resolutions.items():
            print("Resolution = "+parkey)

            # Open the corresponding ROI
            print("Open the corresponding ROI")
            for vol in self.inputs.roi_volumes:
                if (parkey in vol) or (len(self.inputs.roi_volumes)==1):
                    roi_fname = vol
                    print(roi_fname)

            roi = nib.load(roi_fname)
            mask = roi.get_data()

            ## Compute average time-series
            # nROIs: number of ROIs for current resolution
            nROIs = parval['number_of_regions']

            # matrix number of rois vs timepoints
            ts = np.zeros( (nROIs,tp), dtype = np.float32 )

            # loop throughout all the ROIs (current resolution)
            for i in range(1,nROIs+1):
                ts[i-1,:] = fdata[mask==i].mean( axis = 0 )
            print("ts_shape:",ts.shape)

            np.save( os.path.abspath( 'averageTimeseries_%s.npy' % parkey), ts )
            sio.savemat( os.path.abspath( 'averageTimeseries_%s.mat' % parkey), {'ts':ts} )


        ## Apply scrubbing (if enabled) and compute correlation
        # loop throughout all the resolutions ('scale33', ..., 'scale500')
        for parkey, parval in resolutions.items():
            print("Resolution = "+parkey)

            # Open the corresponding ROI
            print("Open the corresponding ROI")
            for vol in self.inputs.roi_volumes:
                if parkey in vol:
                    roi_fname = vol
                    print roi_fname
            roi       = nib.load(roi_fname)
            roiData   = roi.get_data()

            #Average roi time-series
            ts = np.load(os.path.abspath( 'averageTimeseries_%s.npy' % parkey))

            # nROIs: number of ROIs for current resolution
            nROIs = parval['number_of_regions']

            # Create matrix, add node information from parcellation and recover ROI indexes
            print("Create the connection matrix (%s rois)" % nROIs)
            G     = nx.Graph()
            gp = nx.read_graphml(parval['node_information_graphml'])
            ROI_idx = []
            for u,d in gp.nodes(data=True):
                G.add_node(int(u), d)
                # compute a position for the node based on the mean position of the
                # ROI in voxel coordinates (segmentation volume )
                if self.inputs.parcellation_scheme != "Lausanne2018":
                    G.node[int(u)]['dn_position'] = tuple(np.mean( np.where(mask== int(d["dn_correspondence_id"]) ) , axis = 1))
                    ROI_idx.append(int(d["dn_correspondence_id"]))
                else:
                    G.node[int(u)]['dn_position'] = tuple(np.mean( np.where(mask== int(d["dn_multiscaleID"]) ) , axis = 1))
                    ROI_idx.append(int(d["dn_multiscaleID"]))
            # # matrix number of rois vs timepoints
            # ts = np.zeros( (nROIs,tp), dtype = np.float32 )
            #
            # # loop throughout all the ROIs (current resolution)
            # roi_line = 0
            # for i in ROI_idx:
            #     ts[roi_line,:] = fdata[roiData==i].mean( axis = 0 )
            #     roi_line += 1
            #
            # np.save( os.path.abspath('averageTimeseries_%s.npy' % parkey), ts )
            # sio.savemat( os.path.abspath('averageTimeseries_%s.mat' % parkey), {'TCS':ts} )

            #Censoring time-series
            if self.inputs.apply_scrubbing:
                # load scrubbing FD and DVARS series
                FD = np.load( self.inputs.FD )
                DVARS = np.load( self.inputs.DVARS )
                # evaluate scrubbing mask
                FD_th = self.inputs.FD_th
                DVARS_th = self.inputs.DVARS_th
                FD_mask = np.array(np.nonzero(FD < FD_th))[0,:]
                DVARS_mask = np.array(np.nonzero(DVARS < DVARS_th))[0,:]
                index = np.sort(np.unique(np.concatenate((FD_mask,DVARS_mask)))) + 1
                index = np.concatenate(([0],index))
                log_scrubbing = "DISCARDED time points after scrubbing: " + str(FD.shape[0]-index.shape[0]+1) + " over " + str(FD.shape[0]+1)
                print(log_scrubbing)
                np.save( os.path.abspath( 'tp_after_scrubbing.npy'), index )
                sio.savemat( os.path.abspath('tp_after_scrubbing.mat'), {'index':index} )
                ts_after_scrubbing = ts[:,index]
                np.save( os.path.abspath('averageTimeseries_%s_after_scrubbing.npy' % parkey), ts_after_scrubbing )
                sio.savemat( os.path.abspath('averageTimeseries_%s_after_scrubbing.mat' % parkey), {'ts':ts_after_scrubbing} )
                ts = ts_after_scrubbing
                print('ts.shape : ',ts.shape)

                # initialize connectivity matrix
                nnodes = ts.shape[0]
                i = -1
                for i_signal in ts:
                    i += 1
                    for j in xrange(i,nnodes):
                        j_signal = ts[j,:]
                        value = np.corrcoef(i_signal,j_signal)[0,1]
                        G.add_edge(ROI_idx[i],ROI_idx[j],corr = value)
                    	# fmat[i,j] = value
                		# fmat[j,i] = value
                # np.save( op.join(gconf.get_timeseries(), 'fconnectome_%s_after_scrubbing.npy' % s), fmat )
        		# sio.savemat( op.join(gconf.get_timeseries(), 'fconnectome_%s_after_scrubbing.mat' % s), {'fmat':fmat} )
            else:
                nnodes = ts.shape[0]

                i = -1
                for i_signal in ts:
                    i += 1
                    for j in xrange(i,nnodes):
                        j_signal = ts[j,:]
                        value = np.corrcoef(i_signal,j_signal)[0,1]
                        G.add_edge(ROI_idx[i],ROI_idx[j],corr = value)
                        # fmat[i,j] = value
                        # fmat[j,i] = value
            	# np.save( op.join(gconf.get_timeseries(), 'fconnectome_%s.npy' % s), fmat )
            	# sio.savemat( op.join(gconf.get_timeseries(), 'fconnectome_%s.mat' % s), {'fmat':fmat} )

            # storing network
            if 'gPickle' in self.inputs.output_types:
                nx.write_gpickle(G, 'connectome_%s.gpickle' % parkey)
            if 'mat' in self.inputs.output_types:
                # edges
                size_edges = (parval['number_of_regions'],parval['number_of_regions'])
                edge_keys = G.edges(data=True)[0][2].keys()

                edge_struct = {}
                for edge_key in edge_keys:
                    edge_struct[edge_key] = nx.to_numpy_matrix(G,weight=edge_key)

                # nodes
                size_nodes = parval['number_of_regions']
                node_keys = G.nodes(data=True)[0][1].keys()

                node_struct = {}
                for node_key in node_keys:
                    if node_key == 'dn_position':
                        node_arr = np.zeros([size_nodes,3],dtype=np.float)
                    else:
                        node_arr = np.zeros(size_nodes,dtype=np.object_)
                    node_n = 0
                    for _,node_data in G.nodes(data=True):
                        node_arr[node_n] = node_data[node_key]
                        node_n += 1
                    node_struct[node_key] = node_arr

                sio.savemat('connectome_%s.mat' % parkey, mdict={'sc':edge_struct,'nodes':node_struct})
            if 'graphml' in self.inputs.output_types and self.inputs.parcellation_scheme != "Lausanne2018":
                g2 = nx.Graph()
                for u_gml,d_gml in G.nodes(data=True):
                    g2.add_node(u_gml,{'dn_correspondence_id':d_gml['dn_correspondence_id'],
                                   'dn_fsname':d_gml['dn_fsname'],
                                   'dn_hemisphere':d_gml['dn_hemisphere'],
                                   'dn_name':d_gml['dn_name'],
                                   'dn_position_x':float(d_gml['dn_position'][0]),
                                   'dn_position_y':float(d_gml['dn_position'][1]),
                                   'dn_position_z':float(d_gml['dn_position'][2]),
                                   'dn_region':d_gml['dn_region']})
                for u_gml,v_gml,d_gml in G.edges(data=True):
                    g2.add_edge(u_gml,v_gml,{'corr' : float(d_gml['corr'])})
                nx.write_graphml(g2,'connectome_%s.graphml' % parkey)

            if 'graphml' in self.inputs.output_types and self.inputs.parcellation_scheme == "Lausanne2018":
                g2 = nx.Graph()
                for u_gml,d_gml in G.nodes(data=True):
                    g2.add_node(u_gml,{'dn_multiscaleID':d_gml['dn_multiscaleID'],
                                   'dn_fsname':d_gml['dn_fsname'],
                                   'dn_hemisphere':d_gml['dn_hemisphere'],
                                   'dn_name':d_gml['dn_name'],
                                   'dn_position_x':float(d_gml['dn_position'][0]),
                                   'dn_position_y':float(d_gml['dn_position'][1]),
                                   'dn_position_z':float(d_gml['dn_position'][2]),
                                   'dn_region':d_gml['dn_region']})
                for u_gml,v_gml,d_gml in G.edges(data=True):
                    g2.add_edge(u_gml,v_gml,{'corr' : float(d_gml['corr'])})
                nx.write_graphml(g2,'connectome_%s.graphml' % parkey)

            if 'cff' in self.inputs.output_types:
                cvt = cmtk.CFFConverter()
                cvt.inputs.title = 'Connectome mapper'
                cvt.inputs.nifti_volumes = self.inputs.roi_volumes
                cvt.inputs.gpickled_networks = glob.glob(os.path.abspath("connectome_*.gpickle"))
                cvt.run()

        print("[ DONE ]")
        return runtime

    def _list_outputs(self):
        outputs = self._outputs().get()
        outputs['connectivity_matrices'] = glob.glob(os.path.abspath('connectome*'))
        outputs['avg_timeseries'] = glob.glob(os.path.abspath('averageTimeseries_*'))
        if self.inputs.apply_scrubbing:
            outputs['scrubbed_idx'] = os.path.abspath('tp_after_scrubbing.npy')
        return outputs

class ConnectomeStage(Stage):

    def __init__(self):
        self.name = 'connectome_stage'
        self.config = ConnectomeConfig()
        self.inputs = ["roi_volumes_registered","func_file", "FD","DVARS",
                  "parcellation_scheme","atlas_info","roi_graphMLs"]
        self.outputs = ["connectivity_matrices","avg_timeseries"]


    def create_workflow(self, flow, inputnode, outputnode):
        cmtk_cmat = pe.Node(interface=rsfmri_conmat(),name="compute_matrice")
        cmtk_cmat.inputs.output_types = self.config.output_types
        cmtk_cmat.inputs.apply_scrubbing = self.config.apply_scrubbing
        cmtk_cmat.inputs.FD_th = self.config.FD_thr
        cmtk_cmat.inputs.DVARS_th = self.config.DVARS_thr

        flow.connect([
                     (inputnode,cmtk_cmat, [('func_file','func_file'),("FD","FD"),("DVARS","DVARS"),('parcellation_scheme','parcellation_scheme'),('atlas_info','atlas_info'),('roi_volumes_registered','roi_volumes'),('roi_graphMLs','roi_graphmls')]),
                     (cmtk_cmat,outputnode, [('connectivity_matrices','connectivity_matrices'),("avg_timeseries","avg_timeseries")])
                     ])

    def define_inspect_outputs(self):
        con_results_path = os.path.join(self.stage_dir,"compute_matrice","result_compute_matrice.pklz")
        # print('con_results_path : ',con_results_path)
        if(os.path.exists(con_results_path)):

            con_results = pickle.load(gzip.open(con_results_path))
            # print(con_results)

            if isinstance(con_results.outputs.connectivity_matrices, basestring):
                mat = con_results.outputs.connectivity_matrices
                # print(mat)
                if 'gpickle' in mat:
                    self.inspect_outputs_dict['ROI-average time-series correlation - Connectome %s'%os.path.basename(mat)] = ["showmatrix_gpickle",'matrix',mat, "corr", "False", self.config.subject+' - '+con_name+' - Correlation', "default"]
            else:
                for mat in con_results.outputs.connectivity_matrices:
                    # print(mat)
                    if 'gpickle' in mat:
                        con_name = os.path.basename(mat).split(".")[0].split("_")[-1]
                        self.inspect_outputs_dict['ROI-average time-series correlation - Connectome %s'%con_name] = ["showmatrix_gpickle",'matrix',mat, "corr", "False", self.config.subject+' - '+con_name+' - Correlation', "default"]

            self.inspect_outputs = sorted( [key.encode('ascii','ignore') for key in self.inspect_outputs_dict.keys()],key=str.lower)

    def has_run(self):
        return os.path.exists(os.path.join(self.stage_dir,"compute_matrice","result_compute_matrice.pklz"))
