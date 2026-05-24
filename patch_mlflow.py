# patch_mlflow.py
# Must be imported before any mlflow usage

try:
    import mlflow.tracing.processor.mlflow_v2 as _proc_module
    _OrigProcessor = _proc_module.MlflowV2SpanProcessor

    class _PatchedProcessor(_OrigProcessor):
        def on_end(self, span):
            try:
                super().on_end(span)
            except (AttributeError, Exception):
                try:
                    self.span_exporter.export((span,))
                except Exception:
                    pass

    _proc_module.MlflowV2SpanProcessor = _PatchedProcessor
    print("✓ MLflow span processor patched")
except Exception as e:
    print(f"✗ Patch failed: {e}")