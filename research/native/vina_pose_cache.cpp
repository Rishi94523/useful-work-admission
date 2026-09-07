// Research extension: reuse Vina's pair tables only when every atom type matches.
// Caller also enforces the pinned ligand identity, torsion tree and pose geometry.
#include "vina.h"

void Vina::set_ligand_pose_cached(const std::string& text) {
    if (m_sf_choice!=SF_VINA || !m_receptor_initialized || !m_ligand_initialized)
        throw vina_runtime_error("Pose-cache requires initialized rigid-receptor Vina scoring");
    model candidate=m_receptor;
    candidate.append(parse_ligand_pdbqt_from_string(text,m_scoring_function->get_atom_typing()));
    const auto previous=m_model.get_atoms();
    const auto next=candidate.get_atoms();
    if (previous.size()!=next.size()) throw vina_runtime_error("Pose-cache atom count mismatch");
    for (sz i=0;i<previous.size();i++) {
        const auto &a=previous[i], &b=next[i];
        if (a.el!=b.el || a.ad!=b.ad || a.xs!=b.xs || a.sy!=b.sy || a.charge!=b.charge)
            throw vina_runtime_error("Pose-cache atom type mismatch");
    }
    m_model=candidate;
    m_poses=output_container();
}
