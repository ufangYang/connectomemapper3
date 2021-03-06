*****************************************
Outputs of Connectome Mapper 3
*****************************************

Processed, or derivative, data are outputed to ``<bids_dataset/derivatives>/``. 

Main Connectome Mapper Derivatives
==========================================

Main outputs produced by Connectome Mapper 3 are written to ``<bids_dataset/derivatives>/cmp/sub-<subject_label>/``. In this folder, a configuration file generated for each modality pipeline (i.e. anatomical/diffusion/fMRI) and used for processing each participant is saved as ``sub-<subject_label>_anatomical/diffusion/fMRI_config.ini``. It summarizes pipeline workflow options and parameters used for processing. An execution log of the full workflow is saved as `sub-<subject_label>_log.txt``

Anatomical derivatives
------------------------
* Anatomical derivatives in the individual ``T1w`` space are placed in each subject's ``anat/`` subfolder, including:

    * The original T1w image:

        - ``anat/sub-<subject_label>_desc-head_T1w.nii.gz``

    * The masked T1w image with its corresponding brain mask:
    
        - ``anat/sub-<subject_label>_desc-brain_T1w.nii.gz``
        - ``anat/sub-<subject_label>_desc-brain_mask.nii.gz``

    * The segmentations of the white matter (WM), gray matter (GM), and Cortical Spinal Fluid (CSF) tissues:

        - ``anat/sub-<subject_label>_label-WM_dseg.nii.gz``
        - ``anat/sub-<subject_label>_label-GM_dseg.nii.gz``
        - ``anat/sub-<subject_label>_label-CSF_dseg.nii.gz``

    * The five different brain parcellations:

    - ``anat/sub-<subject_label>_label-L2018_desc-<scale_label>_atlas.nii.gz``

        where ``<scale_label>`` : ``scale1``, ``scale2``, ``scale3``, ``scale4``, ``scale5`` corresponds to the parcellation scale.

        with the description of parcel labels and the updated FreeSurfer color lookup table:

        - ``anat/sub-<subject_label>_label-L2018_desc-<scale_label>_atlas.graphml``
        - ``anat/sub-<subject_label>_label-L2018_desc-<scale_label>_atlas_FreeSurferColorLUT.txt``

* Anatomical derivatives in the``DWI`` space produced by the diffusion pipeline are placed in each subject's ``anat/`` subfolder, including:

    * The unmasked T1w image:

        - ``anat/sub-<subject_label>_space-DWI_desc-head_T1w.nii.gz``
    
    * The masked T1w image with its corresponding brain mask:

        - ``anat/sub-<subject_label>_space-DWI_desc-brain_T1w.nii.gz`` 
        - ``anat/sub-<subject_label>_space-DWI_desc-brain_mask.nii.gz``

    * The segmentation of WM tissue used for tractography seeding:

        - ``anat/sub-<subject_label>_space-DWI_label-WM_dseg.nii.gz``

    * The five different brain parcellation are saved as:

        - ``anat/sub-<subject_label>_space-DWI_label-L2018_desc-<scale_label>_atlas.nii.gz``

        where ``<scale_label>`` : ``scale1``, ``scale2``, ``scale3``, ``scale4``, ``scale5`` corresponds to the parcellation scale.

    * The 5TT image used for Anatomically Constrained Tractorgaphy (ACT):

        - ``anat/sub-<subject_label>_space-DWI_label-5TT_probseg.nii.gz``

    * The patial volume maps for white matter (WM), gray matter (GM), and Cortical Spinal Fluid (CSF) used for Particale Filtering Tractography (PFT), generated from 5TT image:

        - ``anat/sub-<subject_label>_space-DWI_label-WM_probseg.nii.gz``
        - ``anat/sub-<subject_label_space-DWI>_label-GM_probseg.nii.gz``
        - ``anat/sub-<subject_label>_space-DWI_label-CSF_probseg.nii.gz``

    * The GM/WM interface used for ACT and PFT seeding:

        - ``anat/sub-<subject_label>_space-DWI_label-GMWMI_probseg.nii.gz``


Diffusion derivatives
------------------------
Diffusion derivatives in the individual ``DWI`` space are placed in each subject's ``dwi/`` subfolder, including:

* The final preprocessed DWI image used to fit the diffusion model for tensor or fiber orientation distribution estimation:
    
    - ``dwi/sub-<subject_label>_desc-preproc_dwi.nii.gz``

* The brain mask used to mask the DWI image:

    - ``dwi/sub-<subject_label>_desc-brain_mask_resampled.nii.gz``

* The diffusion tensor (DTI) fit (if used for tractography):
    
    - ``dwi/sub-<subject_label>]_desc-WLS_model-DTI_diffmodel.nii.gz``
    
    with derived Fractional Anisotropic (FA) and Mean Diffusivity (MD) maps:

    - ``dwi/sub-<subject_label>]_model-DTI_FA.nii.gz``
    - ``dwi/sub-<subject_label>]_model-DTI_MD.nii.gz``


* The Fiber Orientation DIstribution (FOD) image from Constrained Spherical Deconvolution (CSD) fit (if performed):

    - ``dwi/sub-<subject_label>]_model-CSD_diffmodel.nii.gz``


* The MAP-MRI fit for DSI and multi-shell DWI data (if performed):

    - ``dwi/sub-<subject_label>]_model-MAPMRI_diffmodel.nii.gz``

    with derived Generalized Fractional Anisotropic (GFA), Mean Squared Displacement (MSD), Return-to-Origin Probability (RTOP) and Return-to-Plane Probability (RTPP) maps:

    - ``dwi/sub-<subject_label>]_model-MAPMRI_GFA.nii.gz``
    - ``dwi/sub-<subject_label>]_model-MAPMRI_MSD.nii.gz``
    - ``dwi/sub-<subject_label>]_model-MAPMRI_RTOP.nii.gz``
    - ``dwi/sub-<subject_label>]_model-MAPMRI_RTPP.nii.gz``

* The SHORE fit for DSI data:

    - ``dwi/sub-<subject_label>]_model-SHORE_diffmodel.nii.gz``

    with derived Generalized Fractional Anisotropic (GFA), Mean Squared Displacement (MSD), Return-to-Origin Probability (RTOP) maps:

    - ``dwi/sub-<subject_label>]_model-SHORE_GFA.nii.gz``
    - ``dwi/sub-<subject_label>]_model-SHORE_MSD.nii.gz``
    - ``dwi/sub-<subject_label>]_model-SHORE_RTOP.nii.gz``

* The tractogram:

    - ``dwi/sub-<subject_label>_model-<model_label>_desc-<label>_tractogram.trk``

    where:

    - ``<model_label>`` is the diffusion model used to drive tractography (DTI, CSD, SHORE)
    - ``<model_label>`` is the type of tractography algorithm employed (DET for deterministic, PROB for probabilistic)


Functional derivatives
-------------------------------
Functional derivatives in the 'meanBOLD' (individual) space are placed in each subject's ``func/`` subfolder including:

* The original BOLD image: 

    - ``func/sub-<subject_label>_task-rest_desc-cmp_bold.nii.gz``

* The mean BOLD image:

    - ``func/sub-<subject_label>_meanBOLD.nii.gz``

* The fully preprocessed band-pass filtered used to compute ROI time-series: 

    - ``func/sub-<subject_label>_desc-bandpass_task-rest_bold.nii.gz``


* For scrubbing (if enabled):
    
    * The change of variance (DVARS):

        - ``func/sub-<subject_label>_desc-scrubbing_DVARS.npy``

    * The frame displacement (FD):

        - ``func/sub-<subject_label>_desc-scrubbing_FD.npy``

* Motion-related time-series:
    
    - ``func/sub-<subject_label>_motion.tsv``


* The ROI time-series for each parcellation scale:

    - ``func/sub-<subject_label>_atlas-L2018_desc-<scale_label>_timeseries.npy``
    - ``func/sub-<subject_label>_atlas-L2018_desc-<scale_label>_timeseries.mat``

    where ``<scale_label>`` : ``scale1``, ``scale2``, ``scale3``, ``scale4``, ``scale5`` corresponds to the parcellation scale


FreeSurfer Derivatives
=======================

A FreeSurfer subjects directory is created in ``<bids_dataset/derivatives>/freesurfer``.

::

    freesurfer/
        fsaverage/
            mri/
            surf/
            ...
        sub-<subject_label>/
            mri/
            surf/
            ...
        ...

The ``fsaverage`` subject distributed with the running version of FreeSurfer is copied into this directory.

Nipype Workflow Derivatives
==========================================

The execution of each Nipype workflow (pipeline) dedicated to the processing of one modality (i.e. anatomical/diffusion/fMRI) involves the creation of a number of intermediate outputs which are written to ``<bids_dataset/derivatives>/nipype/sub-<subject_label>/<anatomical/diffusion/fMRI>_pipeline`` respectively: 

.. image:: images/nipype_wf_derivatives.png
    :width: 888
    :align: center

To enhance transparency on how data is processed, outputs include a pipeline execution graph saved as ``<anatomical/diffusion/fMRI>_pipeline/graph.svg`` which summarizes all processing nodes involves in the given processing pipeline:

.. image:: images/nipype_wf_graph.png
    :width: 888
    :align: center

Execution details (data provenance) of each interface (node) of a given pipeline are reported in ``<anatomical/diffusion/fMRI>_pipeline/<stage_name>/<interface_name>/_report/report.rst``

.. image:: images/nipype_node_report.png
    :width: 888
    :align: center

.. note:: Connectome Mapper 3 outputs are currently being updated to conform to the :abbr:`BIDS (brain imaging data structure)` Derivatives specification (see `BIDS Derivatives Extension <https://bids-specification.readthedocs.io/en/derivatives/>`_). 
