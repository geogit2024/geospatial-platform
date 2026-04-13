FROM minio/minio:latest
COPY start.sh /start.sh
RUN chmod +x /start.sh
EXPOSE 9000 9001
ENTRYPOINT ["/bin/sh", "/start.sh"]
