.. _installation:

************************************
Installation Instructions for Users
************************************

.. warning:: This software is for research purposes only and shall not be used for
             any clinical use. This software has not been reviewed or approved by
             the Food and Drug Administration or equivalent authority, and is for
             non-clinical, IRB-approved Research Use Only. In no event shall data
             or images generated through the use of the Software be used in the
             provision of patient care.


The Connectome Mapper 3 is composed of a Docker image, namely the Connectome Mapper 3 BIDS App, and a Python Graphical User Interface, namely the Connectome Mapper BIDS App Manager.

* Installation instructions for the Connectome mapper 3 BIDS App are found in :ref:`manual-install-cmpbidsapp`.
* Installation instructions for the Connectome mapper 3 BIDS App Manager are found in :ref:`manual-install-cmpbidsappmanager`.

..
	The steps to add the NeuroDebian repository are explained here::

		$ firefox http://neuro.debian.net/

Make sure that you have installed the following prerequisites.

The Connectome Mapper 3 BIDSApp
===============================

Prerequisites
-------------

* Installed Docker Engine corresponding to your system:

  * For Ubuntu 14.04/16.04/18.04, follow the instructions from the web page::

    $ firefox https://docs.docker.com/install/linux/docker-ce/ubuntu/

  * For Mac OSX (>=10.10.3), get the .dmg installer from the web page::

    $ firefox https://store.docker.com/editions/community/docker-ce-desktop-mac

  * For Windows (>=10), get the installer from the web page::

    $ firefox https://store.docker.com/editions/community/docker-ce-desktop-windows

.. note:: Connectome Mapper 3 BIDSApp has been tested only on Ubuntu and MacOSX. For Windows users, it might be required to make few patches in the Dockerfile.


* Docker managed as a non-root user

  * Open a terminal

  * Create the docker group::

    $ sudo groupadd docker

  * Add the current user to the docker group::

    $ sudo usermod -G docker -a $USER

  * Reboot

    After reboot, test if docker is managed as non-root::

      $ docker run hello-world


.. _manual-install-cmpbidsapp:

Installation
---------------------------------------

Installation of the Connectome Mapper 3 has been facilitated through the distribution of a BIDSApp relying on the Docker software container technology.

* Open a terminal

* Get the latest release (|release|) of the BIDS App:

  .. parsed-literal::

    $ docker pull sebastientourbier/connectomemapper-bidsapp:|release|

* To display all docker images available::

  $ docker images

You should see the docker image "connectomemapper-bidsapp" with tag "|release|" is now available.

* You are ready to use the Connectome Mapper 3 BIDS App from the terminal. See its `commandline usage <usage.html>`_.


The Connectome Mapper 3 BIDSApp Manager (GUI)
==============================================

Prerequisites
---------------

* Installed miniconda2 (Python 2.7) from the web page::

  $ firefox https://conda.io/miniconda.html

  Download the Python 2.7 installer corresponding to your 32/64bits MacOSX/Linux/Win system.


.. _manual-install-cmpbidsappmanager:

Installation
---------------------------------------
The installation of the Connectome Mapper 3 BIDS App Manager (CMPBIDSAPPManager) consists of a clone of the source code repository, the creation of conda environment with all python dependencies installed, and eventually the installation of the CMPBIDSAPPManager itself, as follows:

* Open a terminal

* Go to the folder in which you would like to clone the source code repository::

  $ cd <INSTALLATION DIRECTORY>

* Clone the source code repository::

  $ git clone https://github.com/connectomicslab/connectomemapper3.git connectomemapper3

* Create a branch and checkout the code corresponding to this version release:

  .. parsed-literal::

    $ git fetch
    $ git checkout tags/|release| -b |release|

* Create a miniconda2 environment where all python dependencies will be installed, this by using the spec list "conda_packages_list.txt" provided by the repository::

	$ conda env create -f connectomemapper3/environment.yml

.. important::
  It seems there is no conda package for `git-annex` available on Mac.
  Git-annex should be installed on MacOSX using brew (https://brew.sh/index_fr):

    ``` 
    $ brew install git-annex
    ```
  
  Note that `git-annex` is only necessary if you wish to use BIDS datasets managed by Datalad (https://www.datalad.org/), a very experimental feature. For the moment, I would not recommend to use right now as it has been a long time it has not been tested.

  So, you can without any problem delete or comment the line `- git-annex=7.20190219` and all other lines related to datalad packages in the `environment.yml` and it should then work!

* Activate the conda environment::

  $ source activate py27cmp-gui

  or::

  $ conda activate py27cmp-gui

* Install the Connectome Mapper BIDS App Manager from the Bash Shell using following commands::

	(py27cmp-gui)$ cd connectomemapper3/
	(py27cmp-gui)$ python setup_gui.py install

* You are ready to use the Connectome Mapper 3 BIDS App Manager. See the `dedicated user guide <bidsappmanager.html>`_.

Help/Questions
--------------

If you run into any problems or have any questions, you can post to the `CMTK-users group <http://groups.google.com/group/cmtk-users>`_. Code bugs can be reported by creating a "New Issue" on the `source code repository <https://github.com/connectomicslab/connectomemapper3/issues>`_.
