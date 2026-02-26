FROM python:3.12-slim

# Remove any inherited proxy configuration so apt uses direct connection
RUN rm -f /etc/apt/apt.conf.d/*proxy* || true
ENV http_proxy=""
ENV https_proxy=""
ENV HTTP_PROXY=""
ENV HTTPS_PROXY=""
ENV ALL_PROXY=""
ENV all_proxy=""

RUN http_proxy= https_proxy= HTTP_PROXY= HTTPS_PROXY= ALL_PROXY= all_proxy= \
    apt-get update && \
    apt-get install -y --no-install-recommends \
      openssh-client sshpass curl && \
    rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir ansible-core

WORKDIR /ansible
COPY ansible.cfg /ansible/ansible.cfg
COPY metrics_exporter.py /ansible/metrics_exporter.py

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
CMD ["sleep", "infinity"]
