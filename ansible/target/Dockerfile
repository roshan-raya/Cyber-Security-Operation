FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive

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
      openssh-server sudo curl python3 python3-apt ca-certificates && \
    rm -rf /var/lib/apt/lists/*

RUN useradd -m -s /bin/bash devops \
    && usermod -aG sudo devops \
    && echo 'devops ALL=(ALL) NOPASSWD:ALL' > /etc/sudoers.d/devops \
    && chmod 440 /etc/sudoers.d/devops

RUN mkdir -p /home/devops/.ssh \
    && chown devops:devops /home/devops/.ssh \
    && chmod 700 /home/devops/.ssh

RUN sed -i 's/#PasswordAuthentication yes/PasswordAuthentication no/' /etc/ssh/sshd_config \
    && sed -i 's/#PubkeyAuthentication yes/PubkeyAuthentication yes/' /etc/ssh/sshd_config \
    && echo 'PubkeyAuthentication yes' >> /etc/ssh/sshd_config \
    && echo 'PermitRootLogin no' >> /etc/ssh/sshd_config \
    && sed -i 's/#StrictModes yes/StrictModes yes/' /etc/ssh/sshd_config \
    && grep -q '^StrictModes' /etc/ssh/sshd_config || echo 'StrictModes yes' >> /etc/ssh/sshd_config

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 22

ENTRYPOINT ["/entrypoint.sh"]
