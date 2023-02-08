FROM ubuntu:latest

# Install basic packages
RUN apt update
RUN apt install -y openssl ca-certificates python3 python3-pip netcat iputils-ping iproute2

# Set up certificates
ARG cert_location=/usr/local/share/ca-certificates
RUN mkdir -p ${cert_location}
# Get certificate from "github.com"
RUN openssl s_client -showcerts -connect github.com:443 </dev/null 2>/dev/null|openssl x509 -outform PEM > ${cert_location}/github.crt
# Update certificates
RUN update-ca-certificates

COPY chat /app/chat
WORKDIR /app/chat
RUN pip3 install rpyc
ENTRYPOINT /bin/bash
