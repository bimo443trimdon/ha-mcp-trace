ARG BUILD_FROM
FROM ${BUILD_FROM}

RUN apk add --no-cache python3 py3-pip

COPY package /tmp/package
RUN pip3 install --no-cache-dir --break-system-packages /tmp/package && \
    rm -rf /tmp/package

COPY www /www
COPY guide_server.py /guide_server.py
COPY run.sh /run.sh
RUN chmod +x /run.sh

CMD ["/run.sh"]
