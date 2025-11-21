FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    SSHD_PORT=2222 \
    SSH_AUTH_SOCKET=/tmp/ssh-agent.sock \
    CONFIG_ROOT=/root/.config/simple_sync

WORKDIR /app
COPY . /app

RUN apt-get update && \
    apt-get install -y --no-install-recommends openssh-server openssh-client && \
    rm -rf /var/lib/apt/lists/* && \
    mkdir -p /var/run/sshd /root/.ssh /srv/local /srv/remote && \
    pip install --no-cache-dir .

COPY docker/ssh-agent/sshd_config /etc/ssh/sshd_config
COPY docker/ssh-agent/entrypoint.sh /entrypoint.sh
RUN chmod 600 /etc/ssh/sshd_config && chmod +x /entrypoint.sh

EXPOSE 2222
ENTRYPOINT ["/entrypoint.sh"]
