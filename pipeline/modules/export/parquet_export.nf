process PARQUET_EXPORT {
    tag   { meta.id }
    label 'process_low'
    container 'quay.io/biocontainers/pyarrow:15.0.0'

    input:
    tuple val(meta), path(json)

    output:
    tuple val(meta), path("${meta.id}.metrics.parquet"), emit: parquet
    path  "versions.yml",                                emit: versions

    script:
    """
    python3 - <<'PY'
    import json, pyarrow as pa, pyarrow.parquet as pq
    with open("${json}") as fh:
        rec = json.load(fh)
    # Flatten one level for a tabular, dashboard-friendly Parquet row
    flat = {}
    for k, v in rec.items():
        if isinstance(v, dict):
            for kk, vv in v.items():
                flat[f"{k}.{kk}"] = vv
        else:
            flat[k] = v
    table = pa.table({k: [v] for k, v in flat.items()})
    pq.write_table(table, "${meta.id}.metrics.parquet")
    PY

    printf '"%s":\\n    pyarrow: %s\\n' "${task.process}" "\$(python3 -c 'import pyarrow; print(pyarrow.__version__)')" > versions.yml
    """

    stub:
    """
    touch ${meta.id}.metrics.parquet
    printf '"%s":\\n    pyarrow: 15.0.0\\n' "${task.process}" > versions.yml
    """
}
