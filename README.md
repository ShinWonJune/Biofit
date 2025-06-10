# C&S Project 2025 - Team G

## HaruFit
Smart Daily Routines based on personal data

*This repository is a collection of prerequisites and guidance for team project activities.


## Directory Structure

The directory structure below must be followed, and must be periodically updated in order to be recognized for contributions in external activities such as presentations.

```
.
├── ./ai_service
│   ├── ./ai_service/catboost_info
│   │   ├── ./ai_service/catboost_info/learn
│   │   └── ./ai_service/catboost_info/tmp
│   ├── ./ai_service/models                  # pretrained LLM model saved here
├── ./data_service
│   ├── ./data_service/fitbit_csv            # if you want to test or manual DB, upload your csv that fixed format here
├── ./db
│   └── ./db/init
│       └── ./db/init/@eaDir
├── ./docs                                   # Fitbit auth information record and our team PPT here
├── ./feedback_api                           # User side page
└── ./streamlit_app                          # general pages
```

## Guidelines
실행 방법:
```
unset DOCKER_HOST
docker compose down
docker compose up --build
```


Team members are responsible for taking on tasks appropriate to their roles and submitting them periodically to the appropriate repositories. At this time, please be aware of the following precautions.

* Prohibition of account sharing: The act of pushing someone else's work to your ID is prohibited. **You can only upload your own results with your GitHub account.**
* Periodic upload recommended: Even if the results such as code are incomplete, **please continue to push the progress so that other team members and evaluators can observe and give feedback.** The act of pushing completed results at once is recognized only as a contribution for that date, and efforts in the process are difficult to be recognized.
* Documentation recommended: Documentation in the `docs` directory provided by default will be credited to the author. In addition, even if presentation materials such as PPT are uploaded in binary format, if the contents are listed in the `docs` directory, contributions can be recognized by quoting them.
* Create a `Dockerfile (Containerfile)`: Project artifacts should be able to be packaged into one (or more) container image with the following command: `docker build --tag cs-project-2025-team-xxx .`
    - Build arguments and environment variable dependencies should not be present.
    - **Execution: Execution and usage for containerized images must be documented in `Usage.md` file.**

## Q&A

Please use the `Issues` function to raise inquiries.
