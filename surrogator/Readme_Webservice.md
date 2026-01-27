Surrogator's Webservice
=======================

### Start
-   Run: `python surrogator.py -ws` or
-   Run: `python surrogator.py --webservice`

Screenshot after start (remote or local)

![surrogator_ws_start.png](doc/surrogator_ws_start.png)

### Local Usage 

* use drag and drop with exported INCEpTION projects [(example project)](test_data/projects/project-deid-test-data-1-2025-09-18-160813.zip) or 
* input the place of the path with exported INCEpTION projects (example `test_data/projects`)

![surrogator_ws_start_local.png](doc/surrogator_ws_start_local.png)

### Remote Usage API Mode

-   Download [INCEpTION annotation plattform](https://inception-project.github.io/)
-   Extend `settings.properties` with `remote-api.enabled=true`, follow
    instruction for `ROLE_REMOTE` of the [admin guide of INCEpTION](https://inception-project.github.io/releases/38.0/docs/admin-guide.html)
-   Start INCEpTION.
-   Configure an INCEpTION project with users and documents, add
    `ROLE_REMOTE` in your INCEpTION project(s).
-    The remote usage is running also locally.
-    Use the ip address from INCEpTION as input of the webservice and your login from INCEpTION. 

**After successful import, use the web service and run Quality Control or Surrogation and choose your preferred mode before!**

### Quality Control (Assurance Step)

The Quality Control (Assurance Step) summarizes the annotations in table formatted form:

![surrogator_ws_qc_1.png](doc/surrogator_ws_qc_1.png)
![surrogator_ws_qc_2.png](doc/surrogator_ws_qc_2.png)
![surrogator_ws_qc_3.png](doc/surrogator_ws_qc_3.png)
![surrogator_ws_qc_4.png](doc/surrogator_ws_qc_4.png)

### Surrogation

The output of the surrogation process consists of the download buttons of the PUBLIC archvie and the PRIVATE archive.

**Note**

* We recommend processing only individual projects and reloading the browser after processing!


![surrogator_ws_sg_results.png](doc/surrogator_ws_sg_results.png)
