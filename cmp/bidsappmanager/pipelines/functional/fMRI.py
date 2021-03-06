# Copyright (C) 2009-2017, Ecole Polytechnique Federale de Lausanne (EPFL) and
# Hospital Center and University of Lausanne (UNIL-CHUV), Switzerland
# All rights reserved.
#
#  This software is distributed under the open-source license Modified BSD.

""" Functional pipeline Class definition
"""

import os
import datetime

from traits.api import *
from traitsui.api import *
from traitsui.qt4.extra.qt_view import QtView

from pyface.ui.qt4.image_resource import ImageResource
from pyface.qt.QtCore import *
from pyface.qt.QtGui import *

import nipype.pipeline.engine as pe
from pyface.api import ImageResource

import shutil

from bids import BIDSLayout

# from cmp.bidsappmanager.pipelines.common import *
from cmp.bidsappmanager.pipelines.anatomical.anatomical import AnatomicalPipelineUI
from cmp.bidsappmanager.stages.preprocessing.fmri_preprocessing import PreprocessingStageUI
from cmp.bidsappmanager.stages.segmentation.segmentation import SegmentationStageUI
from cmp.bidsappmanager.stages.parcellation.parcellation import ParcellationStageUI
from cmp.bidsappmanager.stages.registration.registration import RegistrationStageUI
from cmp.bidsappmanager.stages.functional.functionalMRI import FunctionalMRIStageUI
from cmp.bidsappmanager.stages.connectome.fmri_connectome import ConnectomeStageUI

from cmp.pipelines.common import Pipeline
from cmp.pipelines.functional.fMRI import Global_Configuration, Check_Input_Notification, fMRIPipeline


class Check_Input_NotificationUI(Check_Input_Notification):
    traits_view = View(Item('message', style='readonly', show_label=False),
                       Item('imaging_model', editor=EnumEditor(name='imaging_model_options'),
                            visible_when='len(imaging_model_options)>1'),
                       kind='modal',
                       buttons=['OK'],
                       title="Check inputs")


class fMRIPipelineUI(fMRIPipeline):
    view_mode = Enum('config_view', ['config_view', 'inspect_outputs_view'])
    
    preprocessing = Button('Preprocessing')
    functionalMRI = Button('FunctionalMRI')
    registration = Button('Registration')
    connectome = Button('Connectome')
    
    pipeline_group = VGroup(
        HGroup(spring, UItem('preprocessing', style='custom', width=450, height=130, resizable=True,
                             editor_args={'image': ImageResource('preprocessing'), 'label': ""}), spring,
               show_labels=False, label=""),
        HGroup(spring, UItem('registration', style='custom', width=500, height=110, resizable=True,
                             editor_args={'image': ImageResource('registration'), 'label': ""}), spring,
               show_labels=False, label=""),
        HGroup(spring, UItem('functionalMRI', style='custom', width=450, height=240, resizable=True,
                             editor_args={'image': ImageResource('functionalMRI'), 'label': ""}), spring,
               show_labels=False, label=""),
        HGroup(spring, UItem('connectome', style='custom', width=450, height=130, resizable=True,
                             editor_args={'image': ImageResource('connectome'), 'label': ""}), spring,
               show_labels=False, label=""),
        spring,
        springy=True
    )
    
    traits_view = QtView(Include('pipeline_group'))
    
    def __init__(self, project_info):
        
        fMRIPipeline.__init__(self, project_info)
        
        self.stages = {'Preprocessing': PreprocessingStageUI(),
                       'Registration': RegistrationStageUI(pipeline_mode="fMRI"),
                       'FunctionalMRI': FunctionalMRIStageUI(),
                       'Connectome': ConnectomeStageUI()}
        
        for stage in self.stages.keys():
            if project_info.subject_session != '':
                self.stages[stage].stage_dir = os.path.join(self.base_directory, "derivatives", 'nipype', self.subject,
                                                            project_info.subject_session, self.pipeline_name,
                                                            self.stages[stage].name)
            else:
                self.stages[stage].stage_dir = os.path.join(self.base_directory, "derivatives", 'nipype', self.subject,
                                                            self.pipeline_name, self.stages[stage].name)
    
    def _preprocessing_fired(self, info):
        # print("preproc fired")
        self.stages['Preprocessing'].configure_traits(view=self.view_mode)
    
    def _functionalMRI_fired(self, info):
        # print("func fired")
        self.stages['FunctionalMRI'].configure_traits(view=self.view_mode)
    
    def _registration_fired(self, info):
        if self.view_mode == 'config_view':
            self.stages['Registration'].configure_traits(view='config_view_fmri')
        else:
            self.stages['Registration'].configure_traits(view=self.view_mode)
    
    def _connectome_fired(self, info):
        self.stages['Connectome'].configure_traits(view=self.view_mode)
    
    def check_input(self, layout, gui=True):
        print '**** Check Inputs ****'
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
        
        print "Looking for...."
        
        if self.global_conf.subject_session == '':
            
            files = layout.get(subject=subjid, suffix='bold', extensions='.nii.gz')
            if len(files) > 0:
                fmri_file = os.path.join(files[0].dirname, files[0].filename)
                print fmri_file
            else:
                error(message="BOLD image not found for subject %s." % (subjid), title="Error",
                      buttons=['OK', 'Cancel'], parent=None)
                return
            
            files = layout.get(subject=subjid, suffix='bold', extensions='.json')
            if len(files) > 0:
                json_file = os.path.join(files[0].dirname, files[0].filename)
                print json_file
            else:
                error(message="BOLD json sidecar not found for subject %s." % (subjid), title="Warning",
                      buttons=['OK', 'Cancel'], parent=None)
            
            files = layout.get(subject=subjid, suffix='T1w', extensions='.nii.gz')
            if len(files) > 0:
                t1_file = os.path.join(files[0].dirname, files[0].filename)
                print t1_file
            else:
                error(message="T1w image not found for subject %s." % (subjid), title="Error", buttons=['OK', 'Cancel'],
                      parent=None)
                return
            
            files = layout.get(subject=subjid, suffix='T2w', extensions='.nii.gz')
            if len(files) > 0:
                t2_file = os.path.join(files[0].dirname, files[0].filename)
                print t2_file
            else:
                error(message="T2w image not found for subject %s." % (subjid), title="Warning",
                      buttons=['OK', 'Cancel'], parent=None)
        
        else:
            sessid = self.global_conf.subject_session.split("-")[1]
            
            files = layout.get(subject=subjid, suffix='bold', extensions='.nii.gz', session=sessid)
            if len(files) > 0:
                fmri_file = os.path.join(files[0].dirname, files[0].filename)
                print fmri_file
            else:
                error(message="BOLD image not found for subject %s, session %s." % (
                subjid, self.global_conf.subject_session), title="Error", buttons=['OK', 'Cancel'], parent=None)
                return
            
            files = layout.get(subject=subjid, suffix='bold', extensions='.json', session=sessid)
            if len(files) > 0:
                json_file = os.path.join(files[0].dirname, files[0].filename)
                print json_file
            else:
                error(message="BOLD json sidecar not found for subject %s, session %s." % (
                subjid, self.global_conf.subject_session), title="Warning", buttons=['OK', 'Cancel'], parent=None)
            
            files = layout.get(subject=subjid, suffix='T1w', extensions='.nii.gz', session=sessid)
            if len(files) > 0:
                t1_file = os.path.join(files[0].dirname, files[0].filename)
                print t1_file
            else:
                error(message="T1w image not found for subject %s, session %s." % (
                subjid, self.global_conf.subject_session), title="Error", buttons=['OK', 'Cancel'], parent=None)
                return
            
            files = layout.get(subject=subjid, suffix='T2w', extensions='.nii.gz', session=sessid)
            if len(files) > 0:
                t2_file = os.path.join(files[0].dirname, files[0].filename)
                print t2_file
            else:
                error(message="T2w image not found for subject %s, session %s." % (
                subjid, self.global_conf.subject_session), title="Warning", buttons=['OK', 'Cancel'], parent=None)
        
        print "fmri_file : %s" % fmri_file
        print "json_file : %s" % json_file
        print "t1_file : %s" % t1_file
        print "t2_file : %s" % t2_file
        
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
