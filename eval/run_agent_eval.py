"""Evaluación fija del agente con las preguntas de eval/agent_questions.json.

Para cada pregunta registra: herramientas llamadas, si llamó la(s) correcta(s), si citó la
fuente esperada, si la respuesta contiene los datos clave, número de iteraciones y la respuesta.

Uso:  python eval/run_agent_eval.py        (requiere LLM_API_KEY en .env)
Salida: eval/results/agent_eval.csv y eval/results/agent_eval.md
"""
from __future__ import annotations

import datetime as dt
import json
import sys
import time
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import pandas as pd  # noqa: E402

from movilidad.agent import LLMConfigError, MobilityAgent  # noqa: E402
from movilidad.planner import Planner  # noqa: E402
from movilidad.rag import DocIndex  # noqa: E402


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s.lower())
    return "".join(c for c in s if not unicodedata.combining(c))


def main():
    spec = json.loads((ROOT / "eval" / "agent_questions.json").read_text(encoding="utf-8"))
    agent = MobilityAgent(planner=Planner(), index=DocIndex(), hour=spec["hora_dashboard"],
                          today=dt.date.fromisoformat(spec["fecha_referencia"]))
    rows = []
    for q in spec["preguntas"]:
        t0 = time.time()
        try:
            res = agent.run(q["pregunta"])
            answer, calls, iters = res.answer, [c["name"] for c in res.tool_calls], res.iterations
            errors = sum("error" in c["result"] for c in res.tool_calls if isinstance(c["result"], dict))
        except LLMConfigError as exc:
            sys.exit(str(exc))
        except Exception as exc:  # error del proveedor: se registra y se sigue
            answer, calls, iters, errors = f"ERROR: {type(exc).__name__}: {exc}", [], 0, 0
        tool_ok = all(any(t in calls for t in alts) for alts in q["herramientas_esperadas"])
        cited = any(norm(c) in norm(answer) for c in q["cita_esperada"])
        content = all(norm(c) in norm(answer) for c in q["debe_contener"])
        rows.append({"id": q["id"], "categoria": q["categoria"], "pregunta": q["pregunta"],
                     "herramientas_llamadas": ", ".join(calls), "herramienta_correcta": tool_ok,
                     "cita_fuente": cited, "contenido_clave": content, "errores_herramienta": errors,
                     "iteraciones": iters, "segundos": round(time.time() - t0, 1), "respuesta": answer})
        print(f"{q['id']}: tool={tool_ok} cita={cited} contenido={content} calls={calls}")
        time.sleep(2)  # respeta límites de la capa gratuita
    df = pd.DataFrame(rows)
    out = ROOT / "eval" / "results"
    out.mkdir(parents=True, exist_ok=True)
    df.to_csv(out / "agent_eval.csv", index=False)
    n = len(df)
    lines = ["# Evaluación del agente", "",
             f"Fecha de referencia: {spec['fecha_referencia']}. Preguntas: {n}.", "",
             f"- Herramienta correcta: {df.herramienta_correcta.sum()}/{n}",
             f"- Cita de la fuente: {df.cita_fuente.sum()}/{n}",
             f"- Contenido clave: {df.contenido_clave.sum()}/{n}", "",
             df.drop(columns=["respuesta", "pregunta"]).to_markdown(index=False), "", "## Respuestas", ""]
    for r in rows:
        lines += [f"### {r['id']} – {r['pregunta']}", "", r["respuesta"], ""]
    (out / "agent_eval.md").write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines[:8]))


if __name__ == "__main__":
    main()
