FROM python:3.11-slim-buster

ARG VERSION=${VERSION}

WORKDIR /inception-reports

RUN pip install --no-cache-dir apt-mirror-updater && apt-mirror-updater -a

RUN apt-get update --yes && \
    apt-get install --yes git

RUN git clone https://github.com/inception-project/inception-reporting-dashboard.git --branch v$VERSION

RUN cd inception-reporting-dashboard

RUN pip install --no-cache-dir inception-reports

ENTRYPOINT [ "inception_reports" ]
