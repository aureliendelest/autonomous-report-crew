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
                    file_name=report_path.name,
                    mime="text/markdown",
                )
            except RuntimeError as e:
                st.error(f"Erreur : {e}")

with tab_history:
    reports = sorted(
        (p for p in OUTPUTS_DIR.glob("*.md") if not p.name.endswith(".audit.md")),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )

    if not reports:
        st.info("Aucun rapport généré pour l'instant.")
    else:
        # Les noms de domaine peuvent contenir des tirets (ex: "ia-entreprise") :
        # on retrouve le bon préfixe en le comparant aux domaines connus plutôt
        # que de couper le nom de fichier au premier tiret.
        known_domains = sorted(list_domains(), key=len, reverse=True)

        def domain_for(path: Path) -> str:
            for known in known_domains:
                if path.name.startswith(f"{known}-"):
                    return known
            return "autre"

        by_domain: dict[str, list[Path]] = {}
        for path in reports:
            by_domain.setdefault(domain_for(path), []).append(path)

        for domain_name in sorted(by_domain):
            st.subheader(domain_name)
            for path in by_domain[domain_name]:
                with st.expander(path.stem):
                    report_text = path.read_text(encoding="utf-8")
                    st.markdown(report_text)
                    st.download_button(
                        "Télécharger le rapport (.md)",
                        data=report_text,
                        file_name=path.name,
                        mime="text/markdown",
                        key=f"download-{path.name}",
                    )
