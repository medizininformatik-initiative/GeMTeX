FROM python:3.11-slim-buster

WORKDIR /inception-reports

RUN apt-get update --yes && \
    apt-get install --yes git

RUN git clone https://github.com/inception-project/inception-reporting-dashboard.git --branch v0.6.2

RUN cd inception-reporting-dashboard

RUN pip install --no-cache-dir inception-reports

ENTRYPOINT [ "inception_reports" ]
