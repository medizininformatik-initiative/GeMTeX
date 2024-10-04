ARG ROOT_CONTAINER=python:3.7-slim
FROM $ROOT_CONTAINER

ARG RECOMMENDER_WORKDIR=/inception_ahd_recommender

WORKDIR $RECOMMENDER_WORKDIR

COPY . .

RUN python -m pip install --upgrade pip
RUN python -m pip install -e . &&\
    python -m pip install -e ".[contrib]"

ENTRYPOINT ["gunicorn"]