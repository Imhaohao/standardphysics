# Bundled model licences

## ObjectDetector.mlpackage

A Core ML conversion of D-FINE nano trained on COCO, made by `ios/scripts/export-detector.sh`.

| | |
| --- | --- |
| Weights | https://huggingface.co/ustc-community/dfine-nano-coco |
| Revision | `066438d3d8f0da137a37b38fdf3368fd4afceced` |
| Weights licence | Apache-2.0 (declared in the model card) |
| Model code | https://github.com/Peterande/D-FINE, Apache-2.0; Hugging Face Transformers port, Apache-2.0 |
| Paper | Peng et al., "D-FINE: Redefine Regression Task in DETRs as Fine-grained Distribution Refinement", arXiv:2410.13842 |

Changes from the original: converted to Core ML with FP16 weights and a fixed 640x640 input, and the
output reduced to each query's best class score, class id and box. The Apache-2.0 licence text is at
https://www.apache.org/licenses/LICENSE-2.0.
