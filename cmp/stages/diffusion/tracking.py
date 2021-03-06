# Copyright (C) 2009-2017, Ecole Polytechnique Federale de Lausanne (EPFL) and
# Hospital Center and University of Lausanne (UNIL-CHUV), Switzerland
# All rights reserved.
#
#  This software is distributed under the open-source license Modified BSD.

""" Tracking methods and workflows of the diffusion stage
"""

from traits.api import *

from nipype.interfaces.base import CommandLine, CommandLineInputSpec, \
    traits, File, TraitedSpec, BaseInterface, BaseInterfaceInputSpec, isdefined, OutputMultiPath, InputMultiPath

from nipype.utils.filemanip import copyfile

import glob
import os
import pkg_resources
import subprocess, shutil
from nipype.utils.filemanip import split_filename

import nipype.pipeline.engine as pe
import nipype.interfaces.utility as util
import nipype.interfaces.freesurfer as fs
import nipype.interfaces.fsl as fsl
from nipype.interfaces.fsl.base import FSLCommand, FSLCommandInputSpec
# import nipype.interfaces.diffusion_toolkit as dtk
import nipype.interfaces.mrtrix as mrtrix
# import nipype.interfaces.camino as camino
import nipype.interfaces.dipy as dipy

#  import nipype.interfaces.camino2trackvis as camino2trackvis
# import cmtklib.interfaces.camino2trackvis as camino2trackvis
from cmtklib.interfaces.mrtrix3 import Erode, StreamlineTrack
from cmtklib.interfaces.fsl import mapped_ProbTrackX
from cmtklib.interfaces.dipy import DirectionGetterTractography, TensorInformedEudXTractography
from cmtklib.interfaces.misc import Tck2Trk, extractHeaderVoxel2WorldMatrix, match_orientations, make_seeds, \
    make_mrtrix_seeds, getCRS2XYZtkRegTransform, transform_trk_CRS2XYZtkReg

from nipype.workflows.misc.utils import get_data_dims, get_vox_dims

import nibabel as nib
import numpy as np

from cmtklib.diffusion import filter_fibers

# import matplotlib.pyplot as plt

from nipype import logging

iflogger = logging.getLogger('nipype.interface')


class Dipy_tracking_config(HasTraits):
    imaging_model = Str
    tracking_mode = Str
    SD = Bool
    number_of_seeds = Int(1000)
    seed_density = Float(1.0,
                         desc="Number of seeds to place along each direction. A density of 2 is the same as [2, 2, 2] and will result in a total of 8 seeds per voxel.")
    fa_thresh = Float(0.2)
    step_size = traits.Float(0.5)
    max_angle = Float(25.0)
    sh_order = Int(8)
    
    use_act = traits.Bool(False,
                          desc='Use FAST for partial volume estimation and Anatomically-Constrained Tractography (ACT) tissue classifier')
    seed_from_gmwmi = traits.Bool(False,
                                  desc="Seed from Grey Matter / White Matter interface (requires Anatomically-Constrained Tractography (ACT))")
    
    # fast_number_of_classes = Int(3)
    
    def _SD_changed(self, new):
        if self.tracking_mode == "Deterministic" and not new:
            self.curvature = 2.0
        elif self.tracking_mode == "Deterministic" and new:
            self.curvature = 0.0
        elif self.tracking_mode == "Probabilistic":
            self.curvature = 1.0
    
    def _tracking_mode_changed(self, new):
        if new == "Deterministic" and not self.SD:
            self.curvature = 2.0
            self.use_act = False
            self.seed_from_gmwmi = False
        elif new == "Deterministic" and self.SD:
            self.curvature = 0.0
            self.use_act = False
            self.seed_from_gmwmi = False
        elif new == "Probabilistic":
            self.curvature = 1.0
    
    def _curvature_changed(self, new):
        if new <= 0.000001:
            self.curvature = 0.0
    
    def _use_act_changed(self, new):
        if new == False:
            self.seed_from_gmwmi = False


class MRtrix_tracking_config(HasTraits):
    tracking_mode = Str
    SD = Bool
    desired_number_of_tracks = Int(1000000)
    # max_number_of_seeds = Int(1000000000)
    curvature = Float(2.0)
    step_size = Float(0.5)
    min_length = Float(5)
    max_length = Float(500)
    angle = Float(45)
    cutoff_value = Float(0.05)
    
    use_act = traits.Bool(True, desc="Anatomically-Constrained Tractography (ACT) based on Freesurfer parcellation")
    seed_from_gmwmi = traits.Bool(False,
                                  desc="Seed from Grey Matter / White Matter interface (requires Anatomically-Constrained Tractography (ACT))")
    crop_at_gmwmi = traits.Bool(True,
                                desc="Crop streamline endpoints more precisely as they cross the GM-WM interface (requires Anatomically-Constrained Tractography (ACT))")
    backtrack = traits.Bool(True,
                            desc="Allow tracks to be truncated (requires Anatomically-Constrained Tractography (ACT))")
    
    def _SD_changed(self, new):
        if self.tracking_mode == "Deterministic" and not new:
            self.curvature = 2.0
        elif self.tracking_mode == "Deterministic" and new:
            self.curvature = 0.0
        elif self.tracking_mode == "Probabilistic":
            self.curvature = 1.0
    
    def _use_act_changed(self, new):
        if new == False:
            self.crop_at_gmwmi = False
            self.seed_from_gmwmi = False
            self.backtrack = False
    
    def _tracking_mode_changed(self, new):
        if new == "Deterministic" and not self.SD:
            self.curvature = 2.0
        elif new == "Deterministic" and self.SD:
            self.curvature = 0.0
        elif new == "Probabilistic":
            self.curvature = 1.0
    
    def _curvature_changed(self, new):
        if new <= 0.000001:
            self.curvature = 0.0


def create_dipy_tracking_flow(config):
    flow = pe.Workflow(name="tracking")
    # inputnode
    inputnode = pe.Node(interface=util.IdentityInterface(
        fields=['DWI', 'fod_file', 'FA', 'T1', 'partial_volumes', 'wm_mask_resampled', 'gmwmi_file', 'gm_registered',
                'bvals', 'bvecs', 'model']), name='inputnode')
    # outputnode
    
    # CRS2XYZtkReg = subprocess.check_output
    
    outputnode = pe.Node(interface=util.IdentityInterface(fields=["track_file"]), name="outputnode")
    
    if not config.SD and config.imaging_model != 'DSI':  # If tensor fitting was used
        dipy_tracking = pe.Node(interface=TensorInformedEudXTractography(), name='dipy_dtieudx_tracking')
        dipy_tracking.inputs.num_seeds = config.number_of_seeds
        dipy_tracking.inputs.fa_thresh = config.fa_thresh
        dipy_tracking.inputs.max_angle = config.max_angle
        dipy_tracking.inputs.step_size = config.step_size
        
        flow.connect([
            # (dipy_seeds,dipy_tracking,[('seed_files','seed_file')]),
            (inputnode, dipy_tracking, [('wm_mask_resampled', 'seed_mask')]),
            (inputnode, dipy_tracking, [('DWI', 'in_file')]),
            (inputnode, dipy_tracking, [('model', 'in_model')]),
            (inputnode, dipy_tracking, [('FA', 'in_fa')]),
            (inputnode, dipy_tracking, [('wm_mask_resampled', 'tracking_mask')]),
            (dipy_tracking, outputnode, [('tracks', 'track_file')])
        ])
    
    else:  # If CSD was used
        if config.tracking_mode == 'Deterministic':
            # dipy_seeds = pe.Node(interface=make_seeds(),name="dipy_seeds")
            # dipy_tracking = pe.Node(interface=dipy.StreamlineTractography(),name="dipy_deterministic_tracking")
            
            # dipy_tracking.inputs.num_seeds = config.number_of_tracks
            # dipy_tracking.inputs.gfa_thresh = config.gfa_thresh
            # dipy_tracking.inputs.peak_threshold = config.peak_thresh
            # dipy_tracking.inputs.min_angle = config.min_angle
            
            # # flow.connect([
            # #               (inputnode,dipy_tracking,[("bvals","bvals")]),
            # #               (inputnode,dipy_tracking,[("bvecs","bvecs")])
            # #             ])
            
            # flow.connect([
            #     (inputnode,dipy_seeds,[('wm_mask_resampled','WM_file')]),
            #     (inputnode,dipy_seeds,[('gm_registered','ROI_files')]),
            #     ])
            
            # flow.connect([
            #     #(dipy_seeds,dipy_tracking,[('seed_files','seed_file')]),
            #     (inputnode,dipy_tracking,[('wm_mask_resampled','seed_mask')]),
            #     (inputnode,dipy_tracking,[('DWI','in_file')]),
            #     (inputnode,dipy_tracking,[('model','in_model')]),
            #     (inputnode,dipy_tracking,[('wm_mask_resampled','tracking_mask')]),
            #     (dipy_tracking,outputnode,[('tracks','track_file')])
            #     ])
            
            dipy_seeds = pe.Node(interface=make_seeds(), name="dipy_seeds")
            dipy_tracking = pe.Node(interface=DirectionGetterTractography(), name="dipy_deterministic_tracking")
            dipy_tracking.inputs.algo = 'deterministic'
            dipy_tracking.inputs.num_seeds = config.number_of_seeds
            dipy_tracking.inputs.fa_thresh = config.fa_thresh
            dipy_tracking.inputs.max_angle = config.max_angle
            dipy_tracking.inputs.step_size = config.step_size
            dipy_tracking.inputs.use_act = config.use_act
            dipy_tracking.inputs.use_act = config.seed_from_gmwmi
            dipy_tracking.inputs.seed_density = config.seed_density
            
            # dipy_tracking.inputs.fast_number_of_classes = config.fast_number_of_classes
            
            if config.imaging_model == 'DSI':
                dipy_tracking.inputs.recon_model = 'SHORE'
            else:
                dipy_tracking.inputs.recon_model = 'CSD'
                dipy_tracking.inputs.recon_order = config.sh_order
            
            # flow.connect([
            #               (inputnode,dipy_tracking,[("bvals","bvals")]),
            #               (inputnode,dipy_tracking,[("bvecs","bvecs")])
            #             ])
            
            # flow.connect([
            #     (inputnode,dipy_seeds,[('wm_mask_resampled','WM_file')]),
            #     (inputnode,dipy_seeds,[('gm_registered','ROI_files')]),
            #     ])
            
            if config.imaging_model == 'DSI':
                flow.connect([
                    (inputnode, dipy_tracking, [('fod_file', 'fod_file')]),
                ])
            
            flow.connect([
                # (dipy_seeds,dipy_tracking,[('seed_files','seed_file')]),
                (inputnode, dipy_tracking, [('DWI', 'in_file')]),
                (inputnode, dipy_tracking, [('partial_volumes', 'in_partial_volume_files')]),
                (inputnode, dipy_tracking, [('model', 'in_model')]),
                (inputnode, dipy_tracking, [('FA', 'in_fa')]),
                (inputnode, dipy_tracking, [('wm_mask_resampled', 'seed_mask')]),
                (inputnode, dipy_tracking, [('gmwmi_file', 'gmwmi_file')]),
                (inputnode, dipy_tracking, [('wm_mask_resampled', 'tracking_mask')]),
                (dipy_tracking, outputnode, [('tracks', 'track_file')])
            ])
        
        
        elif config.tracking_mode == 'Probabilistic':
            
            # dipy_seeds = pe.Node(interface=make_seeds(),name="dipy_seeds")
            #
            # flow.connect([
            #     (inputnode,dipy_seeds,[('wm_mask_resampled','WM_file')]),
            #     (inputnode,dipy_seeds,[('gm_registered','ROI_files')]),
            #     ])
            
            dipy_tracking = pe.Node(interface=DirectionGetterTractography(), name="dipy_probabilistic_tracking")
            dipy_tracking.inputs.algo = 'probabilistic'
            dipy_tracking.inputs.num_seeds = config.number_of_seeds
            dipy_tracking.inputs.fa_thresh = config.fa_thresh
            dipy_tracking.inputs.max_angle = config.max_angle
            dipy_tracking.inputs.step_size = config.step_size
            dipy_tracking.inputs.use_act = config.use_act
            dipy_tracking.inputs.seed_from_gmwmi = config.seed_from_gmwmi
            dipy_tracking.inputs.seed_density = config.seed_density
            # dipy_tracking.inputs.fast_number_of_classes = config.fast_number_of_classes
            
            if config.imaging_model == 'DSI':
                dipy_tracking.inputs.recon_model = 'SHORE'
            else:
                dipy_tracking.inputs.recon_model = 'CSD'
                dipy_tracking.inputs.recon_order = config.sh_order
            
            # flow.connect([
            #               (inputnode,dipy_tracking,[("bvals","bvals")]),
            #               (inputnode,dipy_tracking,[("bvecs","bvecs")])
            #             ])
            
            if config.imaging_model == 'DSI':
                flow.connect([
                    (inputnode, dipy_tracking, [('fod_file', 'fod_file')]),
                ])
            
            flow.connect([
                # (dipy_seeds,dipy_tracking,[('seed_files','seed_file')]),
                (inputnode, dipy_tracking, [('DWI', 'in_file')]),
                (inputnode, dipy_tracking, [('partial_volumes', 'in_partial_volume_files')]),
                (inputnode, dipy_tracking, [('model', 'in_model')]),
                (inputnode, dipy_tracking, [('FA', 'in_fa')]),
                (inputnode, dipy_tracking, [('wm_mask_resampled', 'seed_mask')]),
                (inputnode, dipy_tracking, [('gmwmi_file', 'gmwmi_file')]),
                (inputnode, dipy_tracking, [('wm_mask_resampled', 'tracking_mask')]),
                (dipy_tracking, outputnode, [('tracks', 'track_file')])
            ])
    
    return flow


def get_freesurfer_parcellation(roi_files):
    print "%s" % roi_files[0]
    return roi_files[0]


def create_mrtrix_tracking_flow(config):
    flow = pe.Workflow(name="tracking")
    # inputnode
    inputnode = pe.Node(interface=util.IdentityInterface(
        fields=['DWI', 'wm_mask_resampled', 'gm_registered', 'act_5tt_registered', 'gmwmi_registered', 'grad']),
                        name='inputnode')
    # outputnode
    
    # CRS2XYZtkReg = subprocess.check_output
    
    outputnode = pe.Node(interface=util.IdentityInterface(fields=["track_file"]), name="outputnode")
    
    # Compute single fiber voxel mask
    wm_erode = pe.Node(interface=Erode(out_filename="wm_mask_resampled.nii.gz"), name="wm_erode")
    wm_erode.inputs.number_of_passes = 3
    wm_erode.inputs.filtertype = 'erode'
    
    flow.connect([
        (inputnode, wm_erode, [("wm_mask_resampled", 'in_file')])
    ])
    
    if config.tracking_mode == 'Deterministic':
        mrtrix_seeds = pe.Node(interface=make_mrtrix_seeds(), name="mrtrix_seeds")
        mrtrix_tracking = pe.Node(interface=StreamlineTrack(), name="mrtrix_deterministic_tracking")
        mrtrix_tracking.inputs.desired_number_of_tracks = config.desired_number_of_tracks
        # mrtrix_tracking.inputs.maximum_number_of_seeds = config.max_number_of_seeds
        mrtrix_tracking.inputs.maximum_tract_length = config.max_length
        mrtrix_tracking.inputs.minimum_tract_length = config.min_length
        mrtrix_tracking.inputs.step_size = config.step_size
        mrtrix_tracking.inputs.angle = config.angle
        mrtrix_tracking.inputs.cutoff_value = config.cutoff_value
        
        # mrtrix_tracking.inputs.args = '2>/dev/null'
        if config.curvature >= 0.000001:
            mrtrix_tracking.inputs.rk4 = True
            mrtrix_tracking.inputs.inputmodel = 'SD_Stream'
        else:
            mrtrix_tracking.inputs.inputmodel = 'SD_Stream'
        flow.connect([
            (inputnode, mrtrix_tracking, [("grad", "gradient_encoding_file")])
        ])
        
        voxel2WorldMatrixExtracter = pe.Node(interface=extractHeaderVoxel2WorldMatrix(),
                                             name='voxel2WorldMatrixExtracter')
        
        flow.connect([
            (inputnode, voxel2WorldMatrixExtracter, [("wm_mask_resampled", "in_file")])
        ])
        # transform_trackvisdata = pe.Node(interface=transform_trk_CRS2XYZtkReg(),name='transform_trackvisdata')
        # flow.connect([
        #             (converter,transform_trackvisdata,[('out_file','trackvis_file')]),
        #             (inputnode,transform_trackvisdata,[('wm_mask_resampled','ref_image_file')])
        #             ])
        
        orientation_matcher = pe.Node(interface=match_orientations(), name="orient_matcher")
        
        flow.connect([
            (inputnode, mrtrix_seeds, [('wm_mask_resampled', 'WM_file')]),
            (inputnode, mrtrix_seeds, [('gm_registered', 'ROI_files')]),
        ])
        
        if config.use_act:
            flow.connect([
                (inputnode, mrtrix_tracking, [('act_5tt_registered', 'act_file')]),
            ])
            mrtrix_tracking.inputs.backtrack = config.backtrack
            mrtrix_tracking.inputs.crop_at_gmwmi = config.crop_at_gmwmi
        else:
            flow.connect([
                (inputnode, mrtrix_tracking, [('wm_mask_resampled', 'mask_file')]),
            ])
        
        if config.seed_from_gmwmi:
            flow.connect([
                (inputnode, mrtrix_tracking, [('gmwmi_registered', 'seed_gmwmi')]),
            ])
        else:
            flow.connect([
                (inputnode, mrtrix_tracking, [('wm_mask_resampled', 'seed_file')]),
            ])
        
        # converter = pe.Node(interface=mrtrix.MRTrix2TrackVis(),name="trackvis")
        converter = pe.Node(interface=Tck2Trk(), name="trackvis")
        converter.inputs.out_tracks = 'converted.trk'
        
        flow.connect([
            # (mrtrix_seeds,mrtrix_tracking,[('seed_files','seed_file')]),
            (inputnode, mrtrix_tracking, [('DWI', 'in_file')]),
            # (inputnode,mrtrix_tracking,[('wm_mask_resampled','mask_file')]),
            # (wm_erode, mrtrix_tracking,[('out_file','mask_file')]),
            # (mrtrix_tracking,outputnode,[('tracked','track_file')]),
            # (mrtrix_tracking,converter,[('tracked','in_file')]),
            # (inputnode,converter,[('wm_mask_resampled','image_file')]),
            # (converter,outputnode,[('out_file','track_file')])
            (mrtrix_tracking, converter, [('tracked', 'in_tracks')]),
            (inputnode, converter, [('wm_mask_resampled', 'in_image')]),
            (converter, outputnode, [('out_tracks', 'track_file')])
        ])
        
        # flow.connect([
        #               (inputnode,mrtrix_tracking,[('DWI','in_file'),('wm_mask_resampled','seed_file'),('wm_mask_resampled','mask_file')]),
        #               (mrtrix_tracking,converter,[('tracked','in_file')]),
        #               (inputnode,converter,[('wm_mask_resampled','image_file')]),
        #               (inputnode,converter,[('wm_mask_resampled','registration_image_file')]),
        #               (voxel2WorldMatrixExtracter,converter,[('out_matrix','matrix_file')]),
        #               # (converter,orientation_matcher,[('out_file','trackvis_file')]),
        #               # (inputnode,orientation_matcher,[('wm_mask_resampled','ref_image_file')]),
        #               # (orientation_matcher,outputnode,[('out_file','track_file')])
        #               (mrtrix_tracking,outputnode,[('tracked','track_file')])
        #               #(converter,outputnode,[('out_file','track_file')])
        #               ])
    
    elif config.tracking_mode == 'Probabilistic':
        mrtrix_seeds = pe.Node(interface=make_mrtrix_seeds(), name="mrtrix_seeds")
        mrtrix_tracking = pe.Node(interface=StreamlineTrack(), name="mrtrix_probabilistic_tracking")
        mrtrix_tracking.inputs.desired_number_of_tracks = config.desired_number_of_tracks
        # mrtrix_tracking.inputs.maximum_number_of_seeds = config.max_number_of_seeds
        mrtrix_tracking.inputs.maximum_tract_length = config.max_length
        mrtrix_tracking.inputs.minimum_tract_length = config.min_length
        mrtrix_tracking.inputs.step_size = config.step_size
        mrtrix_tracking.inputs.angle = config.angle
        mrtrix_tracking.inputs.cutoff_value = config.cutoff_value
        # mrtrix_tracking.inputs.args = '2>/dev/null'
        # if config.curvature >= 0.000001:
        #    mrtrix_tracking.inputs.rk4 = True
        if config.SD:
            mrtrix_tracking.inputs.inputmodel = 'iFOD2'
        else:
            mrtrix_tracking.inputs.inputmodel = 'Tensor_Prob'
        # converter = pe.MapNode(interface=mrtrix.MRTrix2TrackVis(),iterfield=['in_file'],name='trackvis')
        converter = pe.Node(interface=Tck2Trk(), name='trackvis')
        converter.inputs.out_tracks = 'converted.trk'
        # orientation_matcher = pe.Node(interface=match_orientation(), name="orient_matcher")
        
        flow.connect([
            (inputnode, mrtrix_seeds, [('wm_mask_resampled', 'WM_file')]),
            (inputnode, mrtrix_seeds, [('gm_registered', 'ROI_files')]),
        ])
        
        if config.use_act:
            flow.connect([
                (inputnode, mrtrix_tracking, [('act_5tt_registered', 'act_file')]),
            ])
            mrtrix_tracking.inputs.backtrack = config.backtrack
            mrtrix_tracking.inputs.crop_at_gmwmi = config.crop_at_gmwmi
        else:
            flow.connect([
                (inputnode, mrtrix_tracking, [('wm_mask_resampled', 'mask_file')]),
            ])
        
        if config.seed_from_gmwmi:
            flow.connect([
                (inputnode, mrtrix_tracking, [('gmwmi_registered', 'seed_gmwmi')]),
            ])
        else:
            flow.connect([
                (inputnode, mrtrix_tracking, [('wm_mask_resampled', 'seed_file')]),
            ])
        
        flow.connect([
            (inputnode, mrtrix_tracking, [('DWI', 'in_file')]),
            # (inputnode,mrtrix_tracking,[('wm_mask_resampled','mask_file')]),
            # (mrtrix_tracking,outputnode,[('tracked','track_file')]),
            ##(mrtrix_tracking,converter,[('tracked','in_file')]),
            # (mrtrix_tracking,converter,[('tracked','in_file')]),
            # (inputnode,converter,[('wm_mask_resampled','image_file')]),
            # # (converter,outputnode,[('out_file','track_file')])
            # (converter,outputnode,[('out_tracks','track_file')])
            # (mrtrix_tracking,converter,[('tracked','in_file')]),
            # (inputnode,converter,[('wm_mask_resampled','image_file')]),
            # (converter,outputnode,[('out_file','track_file')])
            (mrtrix_tracking, converter, [('tracked', 'in_tracks')]),
            (inputnode, converter, [('wm_mask_resampled', 'in_image')]),
            (converter, outputnode, [('out_tracks', 'track_file')])
        ])
    
    return flow
