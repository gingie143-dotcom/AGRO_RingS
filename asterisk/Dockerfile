FROM debian:bookworm-slim AS build
ARG ASTERISK_VERSION=22.11.0
RUN apt-get update && apt-get install -y --no-install-recommends build-essential ca-certificates curl pkg-config libedit-dev libjansson-dev libxml2-dev uuid-dev libsqlite3-dev libssl-dev libncurses-dev python3 && rm -rf /var/lib/apt/lists/*
WORKDIR /build
RUN curl -fsSLO https://downloads.asterisk.org/pub/telephony/asterisk/asterisk-${ASTERISK_VERSION}.tar.gz && curl -fsSLO https://downloads.asterisk.org/pub/telephony/asterisk/asterisk-${ASTERISK_VERSION}.sha256 && sha256sum -c asterisk-${ASTERISK_VERSION}.sha256 && tar -xzf asterisk-${ASTERISK_VERSION}.tar.gz
RUN cd asterisk-${ASTERISK_VERSION} && ./configure --with-pjproject-bundled --with-jansson-bundled=no && make menuselect.makeopts && menuselect/menuselect --disable BUILD_NATIVE menuselect.makeopts && make -j2 && make install DESTDIR=/out && make samples DESTDIR=/out
FROM debian:bookworm-slim
RUN apt-get update && apt-get install -y --no-install-recommends libedit2 libjansson4 libxml2 libsqlite3-0 libssl3 libncurses6 libuuid1 python3 ca-certificates && rm -rf /var/lib/apt/lists/* && useradd --uid 10001 --create-home asterisk
COPY --from=build /out/ /
COPY render.py /render.py
RUN mkdir -p /var/run/asterisk /var/log/asterisk /var/spool/asterisk && chown -R asterisk:asterisk /etc/asterisk /var/lib/asterisk /var/run/asterisk /var/log/asterisk /var/spool/asterisk
USER asterisk
ENTRYPOINT ["python3","/render.py"]
