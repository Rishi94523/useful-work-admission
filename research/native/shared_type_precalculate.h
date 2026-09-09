// Experimental single-worker Vina/Vinardo table sharing. Included after the
// upstream precalculate_element definition; no scoring/search arithmetic changes.
// The pinned XS potentials depend only on the pair of XS types. AD4 is excluded
// because its electrostatic/solvation terms also depend on atom charges.
struct precalculate_byatom {
    using element_ptr = std::shared_ptr<precalculate_element>;
    precalculate_byatom() = default;
    precalculate_byatom(const ScoringFunction& sf, const model& m,
                       fl v=max_fl, fl factor=32) {
        VINA_CHECK(sf.get_atom_typing() == atom_type::XS);
        m_factor=factor; m_cutoff_sqr=sqr(sf.get_cutoff());
        m_max_cutoff_sqr=sqr(sf.get_max_cutoff());
        m_n=sz(factor*m_max_cutoff_sqr)+3;
        VINA_CHECK(factor>epsilon_fl);
        // Only the most recent parameterization is retained globally. Existing
        // models retain their immutable tables through shared_ptr ownership.
        static flv signature;
        static std::map<std::pair<sz,sz>,element_ptr> cache;
        flv wanted=sf.get_weights();
        wanted.push_back(sf.get_choice()); wanted.push_back(factor);
        wanted.push_back(v); wanted.push_back(m_cutoff_sqr);
        wanted.push_back(m_max_cutoff_sqr);
        if(wanted!=signature){cache.clear();signature=wanted;}
        atomv atoms=m.get_atoms();
        m_data=triangular_matrix<element_ptr>(atoms.size(),element_ptr());
        flv rs=calculate_rs();
        VINA_FOR(i,atoms.size()) VINA_RANGE(j,i,atoms.size()) {
            auto key=std::make_pair((std::min)(atoms[i].xs,atoms[j].xs),
                                    (std::max)(atoms[i].xs,atoms[j].xs));
            auto found=cache.find(key);
            if(found==cache.end()) {
                auto p=std::make_shared<precalculate_element>(m_n,factor);
                // Use exactly the original atom overload, including its handling
                // of untyped hydrogen/glue atoms and the original rounding order.
                VINA_FOR_IN(k,p->smooth)
                    p->smooth[k].first=(std::min)(v,sf.eval(atoms[i],atoms[j],rs[k]));
                p->init_from_smooth_fst(rs);
                found=cache.emplace(key,p).first;
            }
            m_data(i,j)=found->second;
        }
    }
    fl eval_fast(sz i,sz j,fl r2) const {
        assert(r2<=m_max_cutoff_sqr);return m_data(i,j)->eval_fast(r2);
    }
    pr eval_deriv(sz i,sz j,fl r2) const {
        assert(r2<=m_max_cutoff_sqr);return m_data(i,j)->eval_deriv(r2);
    }
    sz index_permissive(sz i,sz j) const {return m_data.index_permissive(i,j);}
    fl cutoff_sqr() const {return m_cutoff_sqr;}
    fl max_cutoff_sqr() const {return m_max_cutoff_sqr;}
    sz get_factor() const {return m_factor;}
    void widen(fl left,fl right) {
        // Copy on write: never mutate a table held by another model or the cache.
        flv rs=calculate_rs();
        std::map<const precalculate_element*,element_ptr> widened;
        VINA_FOR(i,m_data.dim()) VINA_RANGE(j,i,m_data.dim()) {
            const auto old=m_data(i,j).get();
            if(!widened.count(old)) {
                auto p=std::make_shared<precalculate_element>(*m_data(i,j));
                p->widen(rs,left,right);widened[old]=p;
            }
            m_data(i,j)=widened.at(old);
        }
    }
private:
    flv calculate_rs() const {
        flv rs(m_n,0);VINA_FOR(i,m_n) rs[i]=std::sqrt(i/m_factor);return rs;
    }
    fl m_factor=0,m_cutoff_sqr=0,m_max_cutoff_sqr=0;
    sz m_n=0;
    triangular_matrix<element_ptr> m_data;
};
