# Copyright (C) 2009-2017, Ecole Polytechnique Federale de Lausanne (EPFL) and
# Hospital Center and University of Lausanne (UNIL-CHUV), Switzerland
# All rights reserved.
#
#  This software is distributed under the open-source license Modified BSD.

""" Functional pipeline Class definition
"""

import os
import datetime

import nipype.pipeline.engine as pe
import nipype.interfaces.io as nio
from nipype.interfaces.utility import Merge
from nipype import config, logging
from nipype.caching import Memory
import shutil

from traits.api import *
import apptools.io.api as io

import nibabel as nib

from bids import BIDSLayout

from cmp.pipelines.common import *
from cmp.pipelines.anatomical.anatomical import AnatomicalPipeline
from cmp.stages.preprocessing.fmri_preprocessing import PreprocessingStage
from cmp.stages.segmentation.segmentation import SegmentationStage
from cmp.stages.parcellation.parcellation import ParcellationStage
from cmp.stages.registration.registration import RegistrationStage
from cmp.stages.functional.functionalMRI import FunctionalMRIStage
from cmp.stages.connectome.fmri_connectome import ConnectomeStage


class Global_Configuration(HasTraits):
    process_type = Str('fMRI')
    imaging_model = Str


class Check_Input_Notification(HasTraits):
    message = Str
    imaging_model_options = List(['fMRI'])
    imaging_model = Str


class fMRIPipeline(Pipeline):
    now = datetime.datetime.now().strftime("%Y%m%d_%H%M")
    pipeline_name = Str("fMRI_pipeline")
    input_folders = ['anat', 'func']
    seg_tool = Str
    
    subject = Str
    subject_directory = Directory
    derivatives_directory = Directory
    
    ordered_stage_list = ['Preprocessing', 'Registration', 'FunctionalMRI', 'Connectome']
    
    global_conf = Global_Configuration()
    
    config_file = Str
    
    parcellation_scheme = Str
    atlas_info = Dict()
    
    subjects_dir = Str
    subject_id = Str
    
    def __init__(self, project_info):
        self.stages = {'Preprocessing': PreprocessingStage(),
                       'Registration': RegistrationStage(pipeline_mode="fMRI",
                                                        fs_subjects_dir=project_info.freesurfer_subjects_dir,
                                                        fs_subject_id=os.path.basename(project_info.freesurfer_subject_id)),
                       'FunctionalMRI': FunctionalMRIStage(),
                       'Connectome': ConnectomeStage()}
        Pipeline.__init__(self, project_info)
        self.stages['FunctionalMRI'].config.on_trait_change(self.update_nuisance_requirements, 'global_nuisance')
        self.stages['FunctionalMRI'].config.on_trait_change(self.update_nuisance_requirements, 'csf')
        self.stages['FunctionalMRI'].config.on_trait_change(self.update_nuisance_requirements, 'wm')
        self.stages['Connectome'].config.on_trait_change(self.update_scrubbing, 'apply_scrubbing')
        
        self.subject = project_info.subject
        
        self.subjects_dir = project_info.freesurfer_subjects_dir
        self.subject_id = project_info.freesurfer_subject_id
        
        self.global_conf.subjects = project_info.subjects
        self.global_conf.subject = self.subject
        
        if len(project_info.subject_sessions) > 0:
            self.global_conf.subject_session = project_info.subject_session
            self.subject_directory = os.path.join(self.base_directory, self.subject, project_info.subject_session)
        else:
            self.global_conf.subject_session = ''
            self.subject_directory = os.path.join(self.base_directory, self.subject)
        
        self.derivatives_directory = os.path.abspath(project_info.output_directory)
        self.output_directory = os.path.abspath(project_info.output_directory)
    
    def _subject_changed(self, new):
        self.stages['Connectome'].config.subject = new
    
    def update_registration(self):
        if self.seg_tool == "Custom segmentation":
            if self.stages['Registration'].config.registration_mode == 'BBregister (FS)':
                self.stages['Registration'].config.registration_mode = 'Linear (FSL)'
            if 'Nonlinear (FSL)' in self.stages['Registration'].config.registration_mode_trait:
                self.stages['Registration'].config.registration_mode_trait = ['Linear (FSL)', 'Nonlinear (FSL)']
            else:
                self.stages['Registration'].config.registration_mode_trait = ['Linear (FSL)']
        else:
            if 'Nonlinear (FSL)' in self.stages['Registration'].config.registration_mode_trait:
                self.stages['Registration'].config.registration_mode_trait = ['Linear (FSL)', 'BBregister (FS)',
                                                                              'Nonlinear (FSL)']
            else:
                self.stages['Registration'].config.registration_mode_trait = ['Linear (FSL)', 'BBregister (FS)']
    
    def update_nuisance_requirements(self):
        self.stages['Registration'].config.apply_to_eroded_brain = self.stages['FunctionalMRI'].config.global_nuisance
        self.stages['Registration'].config.apply_to_eroded_csf = self.stages['FunctionalMRI'].config.csf
        self.stages['Registration'].config.apply_to_eroded_wm = self.stages['FunctionalMRI'].config.wm
    
    def update_scrubbing(self):
        self.stages['FunctionalMRI'].config.scrubbing = self.stages['Connectome'].config.apply_scrubbing
    
    def define_custom_mapping(self, custom_last_stage):
        # start by disabling all stages
        for stage in self.ordered_stage_list:
            self.stages[stage].enabled = False
        # enable until selected one
        for stage in self.ordered_stage_list:
            print('Enable stage : %s' % stage)
            self.stages[stage].enabled = True
            if stage == custom_last_stage:
                break
    
    def check_input(self, layout, gui=True, debug=False):
        print('**** Check Inputs ****')
        fMRI_available = False
        fMRI_json_available = False
        t1_available = False
        t2_available = False
        valid_inputs = False
        
        if self.global_conf.subject_session == '':
            subject = self.subject
        else:
            subject = "_".join((self.subject, self.global_conf.subject_session))
        
        fmri_file = os.path.join(self.subject_directory, 'func', subject + '_task-rest_bold.nii.gz')
        json_file = os.path.join(self.subject_directory, 'func', subject + '_task-rest_bold.json')
        t1_file = os.path.join(self.subject_directory, 'anat', subject + '_T1w.nii.gz')
        t2_file = os.path.join(self.subject_directory, 'anat', subject + '_T2w.nii.gz')
        
        subjid = self.subject.split("-")[1]
        
        print("> Looking for....")
        if self.global_conf.subject_session == '':
            
            files = layout.get(subject=subjid, suffix='bold', extensions='.nii.gz')
            if len(files) > 0:
                fmri_file = os.path.join(files[0].dirname, files[0].filename)
                # print fmri_file
            else:
                print("ERROR : BOLD image not found for subject %s." % (subjid))
                return
            
            files = layout.get(subject=subjid, suffix='bold', extensions='.json')
            if len(files) > 0:
                json_file = os.path.join(files[0].dirname, files[0].filename)
                # print json_file
            else:
                print("WARNING : BOLD json sidecar not found for subject %s." % (subjid))
            
            files = layout.get(subject=subjid, suffix='T2w', extensions='.nii.gz')
            if len(files) > 0:
                t2_file = os.path.join(files[0].dirname, files[0].filename)
                # print t2_file
            else:
                print("WARNING : T2w image not found for subject %s." % (subjid))
        
        else:
            sessid = self.global_conf.subject_session.split("-")[1]
            
            files = layout.get(subject=subjid, suffix='bold', extensions='.nii.gz', session=sessid)
            if len(files) > 0:
                fmri_file = os.path.join(files[0].dirname, files[0].filename)
                # print fmri_file
            else:
                print("ERROR : BOLD image not found for subject %s, session %s." % (
                subjid, self.global_conf.subject_session))
                return
            
            files = layout.get(subject=subjid, suffix='bold', extensions='.json', session=sessid)
            if len(files) > 0:
                json_file = os.path.join(files[0].dirname, files[0].filename)
                # print json_file
            else:
                print("WARNING : BOLD json sidecar not found for subject %s, session %s." % (
                subjid, self.global_conf.subject_session))
            
            files = layout.get(subject=subjid, suffix='T2w', extensions='.nii.gz', session=sessid)
            if len(files) > 0:
                t2_file = os.path.join(files[0].dirname, files[0].filename)
                # print t2_file
            else:
                print("WARNING : T2w image not found for subject %s, session %s." % (
                subjid, self.global_conf.subject_session))
        
        print("... fmri_file : %s" % fmri_file)
        print("... json_file : %s" % json_file)
        print("... t2_file : %s" % t2_file)
        
        # mods = layout.get_modalities()
        # types = layout.get_modalities()
        # print("Available modalities :")
        # for typ in types:
        #     print("-%s" % typ)
        
        if os.path.isfile(t2_file):
            # print("%s available" % typ)
            t2_available = True
        if os.path.isfile(fmri_file):
            # print("%s available" % typ)
            fMRI_available = True
        if os.path.isfile(json_file):
            # print("%s available" % typ)
            fMRI_json_available = True
        
        # print('fMRI :',fMRI_available)
        # print('t1 :',t1_available)
        # print('t2 :',t2_available)
        
        if fMRI_available:
            if self.global_conf.subject_session == '':
                out_dir = os.path.join(self.output_directory, 'cmp', self.subject)
            else:
                out_dir = os.path.join(self.output_directory, 'cmp', self.subject, self.global_conf.subject_session)
            
            out_fmri_file = os.path.join(out_dir, 'func', subject + '_task-rest_desc-cmp_bold.nii.gz')
            shutil.copy(src=fmri_file, dst=out_fmri_file)
            
            valid_inputs = True
            input_message = 'Inputs check finished successfully.\nfMRI data available.'
            
            if t2_available:
                out_t2_file = os.path.join(out_dir, 'anat', subject + '_T2w.nii.gz')
                shutil.copy(src=t2_file, dst=out_t2_file)
                # swap_and_reorient(src_file=os.path.join(self.base_directory,'NIFTI','T2_orig.nii.gz'),
                #                   ref_file=os.path.join(self.base_directory,'NIFTI','fMRI.nii.gz'),
                #                   out_file=os.path.join(self.base_directory,'NIFTI','T2.nii.gz'))
            
            if fMRI_json_available:
                out_json_file = os.path.join(out_dir, 'func', subject + '_task-rest_desc-cmp_bold.json')
                shutil.copy(src=json_file, dst=out_json_file)
        
        else:
            input_message = 'Error during inputs check. \nfMRI data not available (fMRI).'
        
        print(input_message)
        
        # if gui:
        #     # input_notification = Check_Input_Notification(message=input_message, imaging_model='fMRI')
        #     # input_notification.configure_traits()
        #     self.global_conf.imaging_model = input_notification.imaging_model
        #     self.stages['Registration'].config.imaging_model = input_notification.imaging_model
        # else:
        #     self.global_conf.imaging_model = 'fMRI'
        #     self.stages['Registration'].config.imaging_model = 'fMRI'
        
        self.global_conf.imaging_model = 'fMRI'
        self.stages['Registration'].config.imaging_model = 'fMRI'
        
        if t2_available:
            self.stages['Registration'].config.registration_mode_trait = ['FSL (Linear)', 'BBregister (FS)']
        else:
            self.stages['Registration'].config.registration_mode_trait = ['FSL (Linear)']
        
        # self.fill_stages_outputs()
        
        return valid_inputs
    
    def check_config(self):
        if self.stages['FunctionalMRI'].config.motion == True and self.stages[
            'Preprocessing'].config.motion_correction == False:
            return (
                '\n\tMotion signal regression selected but no motion correction set.\t\n\tPlease activate motion correction in the preprocessing configuration window,\n\tor disable the motion signal regression in the functional configuration window.\t\n')
        if self.stages['Connectome'].config.apply_scrubbing == True and self.stages[
            'Preprocessing'].config.motion_correction == False:
            return (
                '\n\tScrubbing applied but no motion correction set.\t\n\tPlease activate motion correction in the preprocessing configutation window,\n\tor disable scrubbing in the connectome configuration window.\t\n')
        return ''
    
    def process(self):
        # Enable the use of the the W3C PROV data model to capture and represent provenance in Nipype
        # config.enable_provenance()
        
        # Process time
        self.now = datetime.datetime.now().strftime("%Y%m%d_%H%M")
        
        if '_' in self.subject:
            self.subject = self.subject.split('_')[0]
        
        old_subject = self.subject
        
        if self.global_conf.subject_session == '':
            cmp_deriv_subject_directory = os.path.join(self.output_directory, "cmp", self.subject)
            nipype_deriv_subject_directory = os.path.join(self.output_directory, "nipype", self.subject)
        else:
            cmp_deriv_subject_directory = os.path.join(self.output_directory, "cmp", self.subject,
                                                       self.global_conf.subject_session)
            nipype_deriv_subject_directory = os.path.join(self.output_directory, "nipype", self.subject,
                                                          self.global_conf.subject_session)
            
            self.subject = "_".join((self.subject, self.global_conf.subject_session))
        
        if not os.path.exists(os.path.join(nipype_deriv_subject_directory, "fMRI_pipeline")):
            try:
                os.makedirs(os.path.join(nipype_deriv_subject_directory, "fMRI_pipeline"))
            except os.error:
                print("%s was already existing" % os.path.join(nipype_deriv_subject_directory, "fMRI_pipeline"))
        
        # Initialization
        if os.path.isfile(os.path.join(nipype_deriv_subject_directory, "fMRI_pipeline", "pypeline.log")):
            os.unlink(os.path.join(nipype_deriv_subject_directory, "fMRI_pipeline", "pypeline.log"))
        config.update_config(
            {'logging': {'log_directory': os.path.join(nipype_deriv_subject_directory, "fMRI_pipeline"),
                         'log_to_file': True},
             'execution': {'remove_unnecessary_outputs': False,
                           'stop_on_first_crash': True, 'stop_on_first_rerun': False,
                           'crashfile_format': "txt"}
             })
        logging.update_logging(config)
        iflogger = logging.getLogger('nipype.interface')
        
        iflogger.info("**** Processing ****")
        
        flow = self.create_pipeline_flow(cmp_deriv_subject_directory=cmp_deriv_subject_directory,
                                         nipype_deriv_subject_directory=nipype_deriv_subject_directory)
        flow.write_graph(graph2use='colored', format='svg', simple_form=False)
        
        # try:
        
        if (self.number_of_cores != 1):
            flow.run(plugin='MultiProc', plugin_args={'n_procs': self.number_of_cores})
        else:
            flow.run()
        
        # self.fill_stages_outputs()
        
        iflogger.info("**** Processing finished ****")
        
        return True, 'Processing sucessful'
        
        self.subject = old_subject
        
        # except:
        #
        #     self.subject = old_subject
        #     iflogger.info("**** Processing terminated :< ****")
        #
        #     return False,'Processing unsucessful'
        
        # # Clean undesired folders/files
        # rm_file_list = ['rh.EC_average','lh.EC_average','fsaverage']
        # for file_to_rm in rm_file_list:
        #     if os.path.exists(os.path.join(self.base_directory,file_to_rm)):
        #         os.remove(os.path.join(self.base_directory,file_to_rm))
        #
        # # copy .ini and log file
        # outdir = os.path.join(self.base_directory,"RESULTS",'fMRI',now)
        # if not os.path.exists(outdir):
        #     os.makedirs(outdir)
        # shutil.copy(self.config_file,outdir)
        # shutil.copy(os.path.join(self.base_directory,'LOG','pypeline.log'),outdir)
        
        # iflogger.info("**** Processing finished ****")
        #
        # return True,'Processing sucessful'
    
    def create_pipeline_flow(self, cmp_deriv_subject_directory, nipype_deriv_subject_directory):
        
        subject_directory = self.subject_directory
        
        # datasource.inputs.subject = self.subject
        
        if self.parcellation_scheme == 'Lausanne2008':
            bids_atlas_label = 'L2008'
        elif self.parcellation_scheme == 'Lausanne2018':
            bids_atlas_label = 'L2018'
        elif self.parcellation_scheme == 'NativeFreesurfer':
            bids_atlas_label = 'Desikan'
        
        # Data sinker for output
        sinker = pe.Node(nio.DataSink(), name="bold_sinker")
        sinker.inputs.base_directory = os.path.join(cmp_deriv_subject_directory)
        
        if self.parcellation_scheme == 'NativeFreesurfer':
            sinker.inputs.substitutions = [
                (
                'eroded_brain_registered.nii.gz', self.subject + '_space-meanBOLD_desc-eroded_label-brain_dseg.nii.gz'),
                ('eroded_csf_registered.nii.gz', self.subject + '_space-meanBOLD_desc-eroded_label-CSF_dseg.nii.gz'),
                ('wm_mask_registered.nii.gz', self.subject + '_space-meanBOLD_label-WM_dseg.nii.gz'),
                ('eroded_wm_registered.nii.gz', self.subject + '_space-meanBOLD_desc-eroded_label-WM_dseg.nii.gz'),
                ('fMRI_despike_st_mcf.nii.gz_mean_reg.nii.gz', self.subject + '_meanBOLD.nii.gz'),
                ('fMRI_despike_st_mcf.nii.gz.par', self.subject + '_motion.par'),
                ('FD.npy', self.subject + '_desc-scrubbing_FD.npy'),
                ('DVARS.npy', self.subject + '_desc-scrubbing_DVARS.npy'),
                ('fMRI_bandpass.nii.gz', self.subject + '_desc-bandpass_task-rest_bold.nii.gz'),
                
                (self.subject + '_label-' + bids_atlas_label + '_atlas_flirt.nii.gz',
                 self.subject + '_space-meanBOLD_label-' + bids_atlas_label + '_atlas.nii.gz'),
                # (self.subject+'_T1w_parc_freesurferaparc_flirt.nii.gz',self.subject+'_space-meanBOLD_label-Desikan_atlas.nii.gz'),
                ('connectome_freesurferaparc', self.subject + '_label-Desikan_conndata-fnetwork_connectivity'),
                ('averageTimeseries_freesurferaparc', self.subject + '_atlas-Desikan_timeseries'),
            
            ]
        else:
            sinker.inputs.substitutions = [
                (
                'eroded_brain_registered.nii.gz', self.subject + '_space-meanBOLD_desc-eroded_label-brain_dseg.nii.gz'),
                ('wm_mask_registered.nii.gz', self.subject + '_space-meanBOLD_label-WM_dseg.nii.gz'),
                ('eroded_csf_registered.nii.gz', self.subject + '_space-meanBOLD_desc-eroded_label-CSF_dseg.nii.gz'),
                ('eroded_wm_registered.nii.gz', self.subject + '_space-meanBOLD_desc-eroded_label-WM_dseg.nii.gz'),
                ('fMRI_despike_st_mcf.nii.gz_mean_reg.nii.gz', self.subject + '_meanBOLD.nii.gz'),
                ('fMRI_despike_st_mcf.nii.gz.par', self.subject + '_motion.tsv'),
                
                ('FD.npy', self.subject + '_desc-scrubbing_FD.npy'),
                ('DVARS.npy', self.subject + '_desc-scrubbing_DVARS.npy'),
                ('fMRI_bandpass.nii.gz', self.subject + '_desc-bandpass_task-rest_bold.nii.gz'),
                
                (self.subject + '_label-' + bids_atlas_label + '_atlas_flirt.nii.gz',
                 self.subject + '_space-meanBOLD_label-' + bids_atlas_label + '_atlas.nii.gz'),
                
                (self.subject + '_label-' + bids_atlas_label + '_desc-scale1_atlas_flirt.nii.gz',
                 self.subject + '_space-meanBOLD_label-' + bids_atlas_label + '_desc-scale1_atlas.nii.gz'),
                (self.subject + '_label-' + bids_atlas_label + '_desc-scale1_atlas_flirt.nii.gz',
                 self.subject + '_space-meanBOLD_label-' + bids_atlas_label + '_desc-scale2_atlas.nii.gz'),
                (self.subject + '_label-' + bids_atlas_label + '_desc-scale1_atlas_flirt.nii.gz',
                 self.subject + '_space-meanBOLD_label-' + bids_atlas_label + '_desc-scale3_atlas.nii.gz'),
                (self.subject + '_label-' + bids_atlas_label + '_desc-scale1_atlas_flirt.nii.gz',
                 self.subject + '_space-meanBOLD_label-' + bids_atlas_label + '_desc-scale4_atlas.nii.gz'),
                (self.subject + '_label-' + bids_atlas_label + '_desc-scale1_atlas_flirt.nii.gz',
                 self.subject + '_space-meanBOLD_label-' + bids_atlas_label + '_desc-scale5_atlas.nii.gz'),
                
                ('connectome_freesurferaparc', self.subject + '_label-Desikan_conndata-fnetwork_connectivity'),
                ('connectome_scale1',
                 self.subject + '_label-' + bids_atlas_label + '_desc-scale1_conndata-fnetwork_connectivity'),
                ('connectome_scale2',
                 self.subject + '_label-' + bids_atlas_label + '_desc-scale2_conndata-fnetwork_connectivity'),
                ('connectome_scale3',
                 self.subject + '_label-' + bids_atlas_label + '_desc-scale3_conndata-fnetwork_connectivity'),
                ('connectome_scale4',
                 self.subject + '_label-' + bids_atlas_label + '_desc-scale4_conndata-fnetwork_connectivity'),
                ('connectome_scale5',
                 self.subject + '_label-' + bids_atlas_label + '_desc-scale5_conndata-fnetwork_connectivity'),
                ('averageTimeseries_scale1', self.subject + '_atlas-' + bids_atlas_label + '_desc-scale1_timeseries'),
                ('averageTimeseries_scale2', self.subject + '_atlas-' + bids_atlas_label + '_desc-scale2_timeseries'),
                ('averageTimeseries_scale3', self.subject + '_atlas-' + bids_atlas_label + '_desc-scale3_timeseries'),
                ('averageTimeseries_scale4', self.subject + '_atlas-' + bids_atlas_label + '_desc-scale4_timeseries'),
                ('averageTimeseries_scale5', self.subject + '_atlas-' + bids_atlas_label + '_desc-scale5_timeseries'),
            
            ]
        
        # Data import
        datasource = pe.Node(interface=nio.DataGrabber(
            outfields=['fMRI', 'T1', 'T2', 'aseg', 'brain', 'brain_mask', 'wm_mask_file', 'wm_eroded', 'brain_eroded',
                       'csf_eroded', 'roi_volume_s1', 'roi_volume_s2', 'roi_volume_s3', 'roi_volume_s4',
                       'roi_volume_s5', 'roi_graphml_s1', 'roi_graphml_s2', 'roi_graphml_s3', 'roi_graphml_s4',
                       'roi_graphml_s5']), name='datasource')
        datasource.inputs.base_directory = cmp_deriv_subject_directory
        datasource.inputs.template = '*'
        datasource.inputs.raise_on_empty = False
        # datasource.inputs.field_template = dict(fMRI='fMRI.nii.gz',T1='T1.nii.gz',T2='T2.nii.gz')
        
        if self.parcellation_scheme == 'NativeFreesurfer':
            datasource.inputs.field_template = dict(fMRI='func/' + self.subject + '_task-rest_desc-cmp_bold.nii.gz',
                                                    T1='anat/' + self.subject + '_desc-head_T1w.nii.gz',
                                                    T2='anat/' + self.subject + '_T2w.nii.gz',
                                                    aseg='anat/' + self.subject + '_desc-aseg_desg.nii.gz',
                                                    brain='anat/' + self.subject + '_desc-brain_T1w.nii.gz',
                                                    brain_mask='anat/' + self.subject + '_desc-brain_mask.nii.gz',
                                                    wm_mask_file='anat/' + self.subject + '_label-WM_dseg.nii.gz',
                                                    wm_eroded='anat/' + self.subject + '_label-WM_desc-eroded_dseg.nii.gz',
                                                    brain_eroded='anat/' + self.subject + '_label-brain_desc-eroded_dseg.nii.gz',
                                                    csf_eroded='anat/' + self.subject + '_label-CSF_desc-eroded_dseg.nii.gz',
                                                    roi_volume_s1='anat/' + self.subject + '_label-Desikan_atlas.nii.gz',
                                                    roi_volume_s2='anat/irrelevant.nii.gz',
                                                    roi_volume_s3='anat/irrelevant.nii.gz',
                                                    roi_volume_s4='anat/irrelevant.nii.gz',
                                                    roi_volume_s5='anat/irrelevant.nii.gz',
                                                    roi_graphml_s1='anat/' + self.subject + '_label-Desikan_atlas.graphml',
                                                    roi_graphml_s2='anat/irrelevant.graphml',
                                                    roi_graphml_s3='anat/irrelevant.graphml',
                                                    roi_graphml_s4='anat/irrelevant.graphml',
                                                    roi_graphml_s5='anat/irrelevant.graphml')
        else:
            datasource.inputs.field_template = dict(fMRI='func/' + self.subject + '_task-rest_desc-cmp_bold.nii.gz',
                                                    T1='anat/' + self.subject + '_desc-head_T1w.nii.gz',
                                                    T2='anat/' + self.subject + '_T2w.nii.gz',
                                                    aseg='anat/' + self.subject + '_desc-aseg_desg.nii.gz',
                                                    brain='anat/' + self.subject + '_desc-brain_T1w.nii.gz',
                                                    brain_mask='anat/' + self.subject + '_desc-brain_mask.nii.gz',
                                                    wm_mask_file='anat/' + self.subject + '_label-WM_dseg.nii.gz',
                                                    wm_eroded='anat/' + self.subject + '_label-WM_desc-eroded_dseg.nii.gz',
                                                    brain_eroded='anat/' + self.subject + '_label-brain_desc-eroded_dseg.nii.gz',
                                                    csf_eroded='anat/' + self.subject + '_label-CSF_desc-eroded_dseg.nii.gz',
                                                    roi_volume_s1='anat/' + self.subject + '_label-' + bids_atlas_label + '_desc-scale1_atlas.nii.gz',
                                                    roi_volume_s2='anat/' + self.subject + '_label-' + bids_atlas_label + '_desc-scale2_atlas.nii.gz',
                                                    roi_volume_s3='anat/' + self.subject + '_label-' + bids_atlas_label + '_desc-scale3_atlas.nii.gz',
                                                    roi_volume_s4='anat/' + self.subject + '_label-' + bids_atlas_label + '_desc-scale4_atlas.nii.gz',
                                                    roi_volume_s5='anat/' + self.subject + '_label-' + bids_atlas_label + '_desc-scale5_atlas.nii.gz',
                                                    roi_graphml_s1='anat/' + self.subject + '_label-' + bids_atlas_label + '_desc-scale1_atlas.graphml',
                                                    roi_graphml_s2='anat/' + self.subject + '_label-' + bids_atlas_label + '_desc-scale2_atlas.graphml',
                                                    roi_graphml_s3='anat/' + self.subject + '_label-' + bids_atlas_label + '_desc-scale3_atlas.graphml',
                                                    roi_graphml_s4='anat/' + self.subject + '_label-' + bids_atlas_label + '_desc-scale4_atlas.graphml',
                                                    roi_graphml_s5='anat/' + self.subject + '_label-' + bids_atlas_label + '_desc-scale5_atlas.graphml')
        
        datasource.inputs.sort_filelist = False
        
        # Clear previous outputs
        self.clear_stages_outputs()
        
        # Create fMRI flow
        fMRI_flow = pe.Workflow(name='fMRI_pipeline', base_dir=os.path.abspath(nipype_deriv_subject_directory))
        fMRI_inputnode = pe.Node(interface=util.IdentityInterface(
            fields=["fMRI", "T1", "T2", "subjects_dir", "subject_id", "wm_mask_file", "roi_volumes", "roi_graphMLs",
                    "wm_eroded", "brain_eroded", "csf_eroded"]), name="inputnode")
        fMRI_inputnode.inputs.parcellation_scheme = self.parcellation_scheme
        fMRI_inputnode.inputs.atlas_info = self.atlas_info
        fMRI_inputnode.subjects_dir = self.subjects_dir
        # fMRI_inputnode.subject_id = self.subject_id
        fMRI_inputnode.subject_id = os.path.basename(self.subject_id)

        # print('fMRI_inputnode.subjects_dir : {}'.format(fMRI_inputnode.subjects_dir))
        # print('fMRI_inputnode.subject_id : {}'.format(fMRI_inputnode.subject_id))
        
        fMRI_outputnode = pe.Node(interface=util.IdentityInterface(fields=["connectivity_matrices"]), name="outputnode")
        fMRI_flow.add_nodes([fMRI_inputnode, fMRI_outputnode])
        
        merge_roi_volumes = pe.Node(interface=Merge(5), name='merge_roi_volumes')
        merge_roi_graphmls = pe.Node(interface=Merge(5), name='merge_roi_graphmls')
        
        def remove_non_existing_scales(roi_volumes):
            out_roi_volumes = []
            for vol in roi_volumes:
                if vol != None: out_roi_volumes.append(vol)
            return out_roi_volumes
        
        fMRI_flow.connect([
            (datasource, merge_roi_volumes,
             [("roi_volume_s1", "in1"), ("roi_volume_s2", "in2"), ("roi_volume_s3", "in3"), ("roi_volume_s4", "in4"),
              ("roi_volume_s5", "in5")])
        ])
        
        fMRI_flow.connect([
            (datasource, merge_roi_graphmls,
             [("roi_graphml_s1", "in1"), ("roi_graphml_s2", "in2"), ("roi_graphml_s3", "in3"),
              ("roi_graphml_s4", "in4"), ("roi_graphml_s5", "in5")])
        ])
        
        fMRI_flow.connect([
            (datasource, fMRI_inputnode,
             [("fMRI", "fMRI"), ("T1", "T1"), ("T2", "T2"), ("aseg", "aseg"), ("wm_mask_file", "wm_mask_file"),
              ("brain_eroded", "brain_eroded"), ("wm_eroded", "wm_eroded"), ("csf_eroded", "csf_eroded")]),
            # ,( "roi_volumes","roi_volumes")])
            (merge_roi_volumes, fMRI_inputnode, [(("out", remove_non_existing_scales), "roi_volumes")]),
            (merge_roi_graphmls, fMRI_inputnode, [(("out", remove_non_existing_scales), "roi_graphMLs")]),
        ])
        
        if self.stages['Preprocessing'].enabled:
            preproc_flow = self.create_stage_flow("Preprocessing")
            fMRI_flow.connect([
                (fMRI_inputnode, preproc_flow, [("fMRI", "inputnode.functional")]),
                (preproc_flow, sinker, [("outputnode.mean_vol", "func.@mean_vol")]),
            ])
        
        if self.stages['Registration'].enabled:
            reg_flow = self.create_stage_flow("Registration")
            fMRI_flow.connect([
                (fMRI_inputnode, reg_flow, [('T1', 'inputnode.T1')]),
                (fMRI_inputnode, reg_flow, [('T2', 'inputnode.T2')]),
                (preproc_flow, reg_flow, [('outputnode.mean_vol', 'inputnode.target')]),
                (fMRI_inputnode, reg_flow,
                 [('wm_mask_file', 'inputnode.wm_mask'), ('roi_volumes', 'inputnode.roi_volumes'),
                  ('brain_eroded', 'inputnode.eroded_brain'), ('wm_eroded', 'inputnode.eroded_wm'),
                  ('csf_eroded', 'inputnode.eroded_csf')]),
                (reg_flow, sinker, [('outputnode.wm_mask_registered_crop', 'anat.@registered_wm'),
                                    ('outputnode.roi_volumes_registered_crop', 'anat.@registered_roi_volumes'),
                                    ('outputnode.eroded_wm_registered_crop', 'anat.@eroded_wm'),
                                    ('outputnode.eroded_csf_registered_crop', 'anat.@eroded_csf'),
                                    ('outputnode.eroded_brain_registered_crop', 'anat.@eroded_brain')]),
            ])
            # if self.stages['FunctionalMRI'].config.global_nuisance:
            #     fMRI_flow.connect([
            #                   (fMRI_inputnode,reg_flow,[('brain_eroded','inputnode.eroded_brain')])
            #                 ])
            # if self.stages['FunctionalMRI'].config.csf:
            #     fMRI_flow.connect([
            #                   (fMRI_inputnode,reg_flow,[('csf_eroded','inputnode.eroded_csf')])
            #                 ])

        
        if self.stages['FunctionalMRI'].enabled:
            func_flow = self.create_stage_flow("FunctionalMRI")
            fMRI_flow.connect([
                (preproc_flow, func_flow, [('outputnode.functional_preproc', 'inputnode.preproc_file')]),
                (reg_flow, func_flow, [('outputnode.wm_mask_registered_crop', 'inputnode.registered_wm'),
                                       ('outputnode.roi_volumes_registered_crop', 'inputnode.registered_roi_volumes'),
                                       ('outputnode.eroded_wm_registered_crop', 'inputnode.eroded_wm'),
                                       ('outputnode.eroded_csf_registered_crop', 'inputnode.eroded_csf'),
                                       ('outputnode.eroded_brain_registered_crop', 'inputnode.eroded_brain')]),
                (func_flow, sinker, [('outputnode.func_file', 'func.@func_file'), ("outputnode.FD", "func.@FD"),
                                     ("outputnode.DVARS", "func.@DVARS")]),
            ])
            if self.stages['FunctionalMRI'].config.scrubbing or self.stages['FunctionalMRI'].config.motion:
                fMRI_flow.connect([
                    (preproc_flow, func_flow, [("outputnode.par_file", "inputnode.motion_par_file")]),
                    (preproc_flow, sinker, [("outputnode.par_file", "func.@motion_par_file")])
                ])
        
        if self.stages['Connectome'].enabled:
            self.stages['Connectome'].config.subject = self.global_conf.subject
            con_flow = self.create_stage_flow("Connectome")
            fMRI_flow.connect([
                (fMRI_inputnode, con_flow, [('parcellation_scheme', 'inputnode.parcellation_scheme'),
                                            ('roi_graphMLs', 'inputnode.roi_graphMLs')]),
                (func_flow, con_flow,
                 [('outputnode.func_file', 'inputnode.func_file'), ("outputnode.FD", "inputnode.FD"),
                  ("outputnode.DVARS", "inputnode.DVARS")]),
                (reg_flow, con_flow, [("outputnode.roi_volumes_registered_crop", "inputnode.roi_volumes_registered")]),
                (con_flow, fMRI_outputnode, [("outputnode.connectivity_matrices", "connectivity_matrices")]),
                (con_flow, sinker, [("outputnode.connectivity_matrices", "connectivity.@connectivity_matrices")]),
                (con_flow, sinker, [("outputnode.avg_timeseries", "func.@avg_timeseries")])
            ])
            
            if self.parcellation_scheme == "Custom":
                fMRI_flow.connect([(fMRI_inputnode, con_flow, [('atlas_info', 'inputnode.atlas_info')])])
        
        return fMRI_flow
