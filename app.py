from pathlib import Path

import streamlit as st

from src.orchestrator import OUTPUTS_DIR, run_pipeline
from src.prompts import list_domains

st.title("Autonomous Report Crew")

tab_new, tab_history = st.tabs(["Nouveau rapport", "Anciens rapports"])

with tab_new:
    domain = st.selectbox("Domaine", list_domains())
    topic = st.text_input("Sujet", placeholder="ex : Olympique de Marseille")
    generate = st.button("Générer le rapport", type="primary")

    if generate:
        if not topic.strip():
            st.error("Merci de renseigner un sujet.")
        else:
            try:
                with st.status("Génération du rapport...", expanded=True) as status:
                    report_path = run_pipeline(topic, domain, on_step=status.write)
                    status.update(label="Rapport généré", state="complete")

                report_text = report_path.read_text(encoding="utf-8")
                st.markdown(report_text)
                st.download_button(
                    "Télécharger le rapport (.md)",
                    data=report_text,
                    file_name=f"{domain}-{report_path.parent.name}.md",
                    mime="text/markdown",
                )
            except RuntimeError as e:
                st.error(f"Erreur : {e}")

with tab_history:
    reports = sorted(
        OUTPUTS_DIR.glob("*/*/report.md"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )

    if not reports:
        st.info("Aucun rapport généré pour l'instant.")
    else:
        by_domain: dict[str, list[Path]] = {}
        for path in reports:
            by_domain.setdefault(path.parent.parent.name, []).append(path)

        for domain_name in sorted(by_domain):
            st.subheader(domain_name)
            for path in by_domain[domain_name]:
                run_name = path.parent.name
                with st.expander(run_name):
                    report_text = path.read_text(encoding="utf-8")
                    st.markdown(report_text)
                    st.download_button(
                        "Télécharger le rapport (.md)",
                        data=report_text,
                        file_name=f"{domain_name}-{run_name}.md",
                        mime="text/markdown",
                        key=f"download-{domain_name}-{run_name}",
                    )
