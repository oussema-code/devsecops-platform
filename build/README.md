# Image maintenance

Each patch applies to one service at the commit in upstream.lock.json. The private
platform repository owns these build changes. The upstream checkout stays independent.

The first release scan (run 42085163342) rejected all eleven images. The patches
update Go builders and x/net, the .NET runtime and SDK, Java libraries and JRE,
Alpine packages, Python dependency locks, and the Node.js telemetry exporters.
The old exporter bundled protobuf tooling that shipped taffydb with no listed fix.
The replacement exporter uses the project's existing OpenTelemetry SDK generation.

Python constraints record the vulnerability remediation floors used to regenerate
the exact requirement locks. Base image changes use registry digests. Alpine's
package index can change between builds. Production promotion reuses the scanned
image digest.

A pull request builds and scans every service with read-only repository access.
Review the patches, reports and SBOMs before merging. The release job on main
applies the same patches and scans the artifacts again before signing and publishing.
