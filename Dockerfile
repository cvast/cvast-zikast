FROM python:2.7

RUN apt-get update -y &&\
	apt-get upgrade -y &&\
	apt-get install -y dos2unix

## Install Postgresql client
RUN echo "deb http://apt.postgresql.org/pub/repos/apt/ trusty-pgdg main" >> /etc/apt/sources.list.d/pgdg.list &&\
	wget --quiet -O - https://www.postgresql.org/media/keys/ACCC4CF8.asc | apt-key add - &&\
	apt-get update -y &&\
	apt-get install -y postgresql-client-9.6

RUN apt-get update -y &&\
    apt-get install -y postgis

# ptvsd = for debugging with Visual Studio Code
RUN pip install psycopg2 ptvsd==3.0.0 pyproj shapely nose

ENV DYCAST_PATH=/dycast
ENV DYCAST_APP_PATH=${DYCAST_PATH}/application
ENV PG_SHARE_PATH=/usr/local/pgsql/share
ENV DOCKER_DIR=/docker
ENV PYTHONPATH=${DYCAST_PATH}:$PYTHONPATH

COPY ./application ${DYCAST_APP_PATH}

# Tests cannot be executable
RUN chmod -R -x ${DYCAST_APP_PATH}/tests

COPY docker/entrypoint.sh ${DOCKER_DIR}/entrypoint.sh
RUN	chmod -R 700 ${DOCKER_DIR} &&\
	dos2unix ${DOCKER_DIR}/*

WORKDIR ${DYCAST_APP_PATH}

# Set entrypoint
ENTRYPOINT ["/docker/entrypoint.sh"]
CMD ["run_dycast"]