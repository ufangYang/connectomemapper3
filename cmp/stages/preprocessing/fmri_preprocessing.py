# Copyright (C) 2009-2017, Ecole Polytechnique Federale de Lausanne (EPFL) and
# Hospital Center and University of Lausanne (UNIL-CHUV), Switzerland
# All rights reserved.
#
#  This software is distributed under the open-source license Modified BSD.

""" CMP fmri first preprocessing Stage 
"""

from traits.api import *
import os
import pickle
import gzip

import nipype.pipeline.engine as pe
import nipype.interfaces.fsl as fsl
from nipype.interfaces import afni
import nipype.interfaces.utility as util

import nibabel as nib

from cmp.stages.common import Stage
from cmtklib.functionalMRI import discard_tp


class PreprocessingConfig(HasTraits):
    discard_n_volumes = Int('5')
    despiking = Bool(True)
    slice_timing = Enum("none",
                        ["bottom-top interleaved", "bottom-top interleaved", "top-bottom interleaved", "bottom-top",
                         "top-bottom"])
    repetition_time = Float(1.92)
    motion_correction = Bool(True)


class PreprocessingStage(Stage):
    # General and UI members
    def __init__(self):
        self.name = 'preprocessing_stage'
        self.config = PreprocessingConfig()
        self.inputs = ["functional"]
        self.outputs = ["functional_preproc", "par_file", "mean_vol"]
    
    def create_workflow(self, flow, inputnode, outputnode):
        discard_output = pe.Node(interface=util.IdentityInterface(fields=["discard_output"]), name="discard_output")
        if self.config.discard_n_volumes > 0:
            discard = pe.Node(interface=discard_tp(n_discard=self.config.discard_n_volumes), name='discard_volumes')
            flow.connect([
                (inputnode, discard, [("functional", "in_file")]),
                (discard, discard_output, [("out_file", "discard_output")])
            ])
        else:
            flow.connect([
                (inputnode, discard_output, [("functional", "discard_output")])
            ])
        
        despiking_output = pe.Node(interface=util.IdentityInterface(fields=["despiking_output"]),
                                   name="despkiking_output")
        if self.config.despiking:
            despike = pe.Node(interface=afni.Despike(out_file='despike+orig.BRIK'), name='afni_despike')
            converter = pe.Node(interface=afni.AFNItoNIFTI(out_file='fMRI_despike.nii.gz'), name='converter')
            flow.connect([
                (discard_output, despike, [("discard_output", "in_file")]),
                (despike, converter, [("out_file", "in_file")]),
                (converter, despiking_output, [("out_file", "despiking_output")])
            ])
        else:
            flow.connect([
                (discard_output, despiking_output, [("discard_output", "despiking_output")])
            ])
        
        if self.config.slice_timing != "none":
            slc_timing = pe.Node(interface=fsl.SliceTimer(), name='slice_timing')
            slc_timing.inputs.time_repetition = self.config.repetition_time
            if self.config.slice_timing == "bottom-top interleaved":
                slc_timing.inputs.interleaved = True
                slc_timing.inputs.index_dir = False
            elif self.config.slice_timing == "top-bottom interleaved":
                slc_timing.inputs.interleaved = True
                slc_timing.inputs.index_dir = True
            elif self.config.slice_timing == "bottom-top":
                slc_timing.inputs.interleaved = False
                slc_timing.inputs.index_dir = False
            elif self.config.slice_timing == "top-bottom":
                slc_timing.inputs.interleaved = False
                slc_timing.inputs.index_dir = True
        
        # def add_header_and_convert_to_tsv(in_file):
        
        #     try:
        
        if self.config.motion_correction:
            mo_corr = pe.Node(interface=fsl.MCFLIRT(stats_imgs=True, save_mats=False, save_plots=True, mean_vol=True),
                              name="motion_correction")
        
        if self.config.slice_timing != "none":
            flow.connect([
                (despiking_output, slc_timing, [("despiking_output", "in_file")])
            ])
            if self.config.motion_correction:
                flow.connect([
                    (slc_timing, mo_corr, [("slice_time_corrected_file", "in_file")]),
                    (mo_corr, outputnode, [("out_file", "functional_preproc")]),
                    (mo_corr, outputnode, [("par_file", "par_file")]),
                    (mo_corr, outputnode, [("mean_img", "mean_vol")]),
                ])
            else:
                mean = pe.Node(interface=fsl.MeanImage(), name="mean")
                flow.connect([
                    (slc_timing, outputnode, [("slice_time_corrected_file", "functional_preproc")]),
                    (slc_timing, mean, [("slice_time_corrected_file", "in_file")]),
                    (mean, outputnode, [("out_file", "mean_vol")])
                ])
        else:
            if self.config.motion_correction:
                flow.connect([
                    (despiking_output, mo_corr, [("despiking_output", "in_file")]),
                    (mo_corr, outputnode, [("out_file", "functional_preproc")]),
                    (mo_corr, outputnode, [("par_file", "par_file")]),
                    (mo_corr, outputnode, [("mean_img", "mean_vol")]),
                ])
            else:
                mean = pe.Node(interface=fsl.MeanImage(), name="mean")
                flow.connect([
                    (despiking_output, outputnode, [("despiking_output", "functional_preproc")]),
                    (inputnode, mean, [("functional", "in_file")]),
                    (mean, outputnode, [("out_file", "mean_vol")])
                ])
    
    def define_inspect_outputs(self):
        # print('Stage (inspect_outputs): '.format(self.stage_dir))
        if self.config.despiking:
            # print('despiking output')
            despike_path = os.path.join(self.stage_dir, "converter", "result_converter.pklz")
            if (os.path.exists(despike_path)):
                # print('exists')
                despike_results = pickle.load(gzip.open(despike_path))
                self.inspect_outputs_dict['Spike corrected image'] = ['fsleyes', '-ad',
                                                                      despike_results.outputs.out_file, '-cm',
                                                                      'brain_colours_blackbdy_iso']
        
        if self.config.slice_timing:
            slc_timing_path = os.path.join(self.stage_dir, "slice_timing", "result_slice_timing.pklz")
            if (os.path.exists(slc_timing_path)):
                slice_results = pickle.load(gzip.open(slc_timing_path))
                self.inspect_outputs_dict['Slice time corrected image'] = ['fsleyes', '-ad',
                                                                           slice_results.outputs.slice_time_corrected_file,
                                                                           '-cm', 'brain_colours_blackbdy_iso']
            if self.config.motion_correction:
                motion_results_path = os.path.join(self.stage_dir, "motion_correction", "result_motion_correction.pklz")
                if (os.path.exists(motion_results_path)):
                    motion_results = pickle.load(gzip.open(motion_results_path))
                    self.inspect_outputs_dict['Slice time and motion corrected image'] = ['fsleyes', '-ad',
                                                                                          motion_results.outputs.out_file,
                                                                                          '-cm',
                                                                                          'brain_colours_blackbdy_iso']
        
        elif self.config.motion_correction:
            motion_results_path = os.path.join(self.stage_dir, "motion_correction", "result_motion_correction.pklz")
            if (os.path.exists(motion_results_path)):
                motion_results = pickle.load(gzip.open(motion_results_path))
                self.inspect_outputs_dict['Motion corrected image'] = ['fsleyes', '-ad',
                                                                       motion_results.outputs.out_file, '-cm',
                                                                       'brain_colours_blackbdy_iso']
        
        self.inspect_outputs = sorted([key.encode('ascii', 'ignore') for key in self.inspect_outputs_dict.keys()],
                                      key=str.lower)
    
    def has_run(self):
        if self.config.motion_correction:
            return os.path.exists(os.path.join(self.stage_dir, "motion_correction", "result_motion_correction.pklz"))
        elif self.config.slice_timing:
            return os.path.exists(os.path.join(self.stage_dir, "slice_timing", "result_slice_timing.pklz"))
        elif self.config.despiking:
            return os.path.exists(os.path.join(self.stage_dir, "converter", "result_converter.pklz"))
        else:
            return True
