# Build from the repository root so the engine crate and the rulepack are in the context:
#   docker build -f server/Dockerfile -t sp-server .
FROM rust:1-bookworm AS build
WORKDIR /repo
COPY core ./core
COPY rules ./rules
COPY server ./server
WORKDIR /repo/server
RUN cargo build --release --locked --bin sp-server

FROM gcr.io/distroless/cc-debian12:nonroot
COPY --from=build /repo/server/target/release/sp-server /usr/local/bin/sp-server
ENV PORT=8080 LOG_FORMAT=json
EXPOSE 8080
ENTRYPOINT ["/usr/local/bin/sp-server"]
CMD ["serve"]
