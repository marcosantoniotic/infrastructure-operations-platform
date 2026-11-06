# Build only in an isolated environment. Record resolved base digests in evidence.
FROM golang:1.27.3-alpine AS builder
RUN apk add --no-cache git python3
WORKDIR /build
RUN git clone https://github.com/unpoller/unpoller.git unpoller && \
    git -C unpoller checkout d9f4fcbe2c41841a0dd0d0591b98a4a4c4a71c70 && \
    git clone https://github.com/unpoller/unifi.git unifi && \
    git -C unifi checkout ef31b28fd458d777066533990054b6d7fea95043
COPY scripts/ci/patch-unifi-ocsp.py /build/iop/scripts/ci/patch-unifi-ocsp.py
COPY roles/observability/files/unifi-ocsp-transport.go /build/iop/roles/observability/files/unifi-ocsp-transport.go
RUN python3 /build/iop/scripts/ci/patch-unifi-ocsp.py /build/unifi && \
    cd /build/unpoller && go mod edit -replace github.com/unpoller/unifi/v5=../unifi && \
    CGO_ENABLED=0 go build -trimpath -o /build/unpoller-bin .

FROM python:3.13.12-alpine3.23
RUN apk add --no-cache ca-certificates && pip install --no-cache-dir cryptography==50.0.2
RUN mkdir -p /opt/iop /etc/unpoller && chmod 0755 /opt/iop /etc/unpoller
COPY --from=builder --chmod=0755 /build/unpoller-bin /usr/bin/unpoller
COPY --chmod=0644 containers/unifi-ocsp/up.conf /etc/unpoller/up.conf
LABEL io.iop.ocsp.enforcement="connection-v1"
LABEL io.iop.ocsp.policy-options="certid-freshness-v1"
COPY --chmod=0644 roles/observability/files/unifi_ocsp.py /opt/iop/unifi_ocsp.py
COPY --chmod=0644 roles/observability/files/unifi-ap-counts.py /opt/iop/unifi-ap-counts.py
ENV IOP_UNIFI_OCSP_PYTHON=/usr/local/bin/python3 IOP_UNIFI_OCSP_VERIFIER=/opt/iop/unifi_ocsp.py
USER 10001:10001
RUN test -r /opt/iop/unifi_ocsp.py && test -r /opt/iop/unifi-ap-counts.py && test -x /usr/bin/unpoller
ENTRYPOINT ["/usr/bin/unpoller"]
