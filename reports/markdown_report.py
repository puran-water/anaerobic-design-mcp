"""Markdown report generation with Jinja2 templates and Obsidian support."""

import json
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional


class MarkdownReportBuilder:
    """Generates Markdown reports from anaerobic design data with Obsidian frontmatter."""

    def __init__(self):
        self.output_dir = Path(__file__).parent / "output"
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Lazy-load Jinja2 to avoid import at startup
        self._env = None

    @property
    def env(self):
        """Lazy-load Jinja2 environment."""
        if self._env is None:
            from jinja2 import Environment, FileSystemLoader, select_autoescape

            template_dir = Path(__file__).parent / "templates"
            self._env = Environment(
                loader=FileSystemLoader(str(template_dir)),
                autoescape=select_autoescape(['html', 'xml']),
                trim_blocks=True,
                lstrip_blocks=True
            )
            # Add custom filters
            self._env.filters['format_value'] = self._format_value
        return self._env

    def _format_value(self, value, precision=1, default='-'):
        """Format numeric values with precision, or show default for missing."""
        if value is None or value == '':
            return default
        if isinstance(value, (int, float)):
            return f"{value:.{precision}f}"
        return str(value)

    def generate(self, job_id: Optional[str] = None, output_format: str = "markdown") -> Dict[str, str]:
        """Generate report from design state and simulation results.

        Args:
            job_id: Optional job ID to load results from specific job directory
            output_format: Output format (currently only "markdown" supported)

        Returns:
            Dict with path to generated report file
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        # Determine data source directories
        if job_id:
            job_dir = Path(f"jobs/{job_id}")
            if not job_dir.exists():
                raise FileNotFoundError(f"Job directory not found: {job_dir}")
        else:
            job_dir = None

        # Load all data sources
        basis = self._load_json(job_dir, "basis.json", Path("state/basis_of_design.json"))
        adm1_state = self._load_json(job_dir, "adm1_state.json", Path("adm1_state.json"))
        heuristic_config = self._load_json(job_dir, "heuristic_config.json", Path("state/heuristic_config.json"))
        performance = self._load_json(job_dir, "simulation_performance.json")
        inhibition = self._load_json(job_dir, "simulation_inhibition.json")
        precipitation = self._load_json(job_dir, "simulation_precipitation.json")

        # Prepare template context
        context = self._prepare_context(
            basis=basis,
            adm1_state=adm1_state,
            heuristic_config=heuristic_config,
            performance=performance,
            inhibition=inhibition,
            precipitation=precipitation
        )

        # Generate markdown content
        markdown_content = self._generate_markdown(context)

        # Save markdown file
        project_name = context.get('project_name', 'Anaerobic_Design')
        # Sanitize filename
        project_name = project_name.replace(' ', '_').replace('/', '_').replace('\\', '_').replace(':', '-')
        md_path = self.output_dir / f"{project_name}_{timestamp}.md"
        with open(md_path, "w", encoding='utf-8') as f:
            f.write(markdown_content)

        return {"markdown": str(md_path), "status": "success"}

    def _load_json(self, job_dir: Optional[Path], filename: str, fallback: Optional[Path] = None) -> Dict:
        """Load JSON file from job directory or fallback location."""
        if job_dir:
            path = job_dir / filename
            if path.exists():
                with open(path, "r") as f:
                    return json.load(f)

        # Try fallback paths
        if fallback and fallback.exists():
            with open(fallback, "r") as f:
                return json.load(f)

        # Try current directory
        if Path(filename).exists():
            with open(filename, "r") as f:
                return json.load(f)

        return {}

    def _prepare_context(
        self,
        basis: Dict,
        adm1_state: Dict,
        heuristic_config: Dict,
        performance: Dict,
        inhibition: Dict,
        precipitation: Dict
    ) -> Dict[str, Any]:
        """Prepare template context from all data sources."""
        context = {
            'timestamp': datetime.now().isoformat(),
            'timestamp_readable': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'status': 'draft'
        }

        # === Basis of Design ===
        context['flow_m3d'] = basis.get('Q', 0)
        context['cod_mg_l'] = basis.get('cod_mg_l', 0)
        context['tss_mg_l'] = basis.get('tss_mg_l', 0)
        context['vss_mg_l'] = basis.get('vss_mg_l', 0)
        context['tkn_mg_l'] = basis.get('tkn_mg_l', 0)
        context['tp_mg_l'] = basis.get('tp_mg_l', 0)
        context['ph'] = basis.get('ph', basis.get('pH', 7.0))
        context['alkalinity_meq_l'] = basis.get('alkalinity_meq_l', 0)

        # Temperature handling (may be in Kelvin)
        temp = basis.get('Temp', basis.get('temperature_c', 35))
        if temp > 100:  # Likely Kelvin
            context['temperature_c'] = temp - 273.15
        else:
            context['temperature_c'] = temp

        # Mass loadings
        Q = context['flow_m3d']
        context['cod_load_kg_d'] = Q * context['cod_mg_l'] / 1000
        context['tss_load_kg_d'] = Q * context['tss_mg_l'] / 1000
        context['vss_load_kg_d'] = Q * context['vss_mg_l'] / 1000
        context['tkn_load_kg_d'] = Q * context['tkn_mg_l'] / 1000
        context['tp_load_kg_d'] = Q * context['tp_mg_l'] / 1000

        # Feedstock type inference
        cod = context['cod_mg_l']
        if cod > 20000:
            context['feedstock_type'] = 'High-strength industrial'
        elif cod > 5000:
            context['feedstock_type'] = 'Industrial wastewater'
        elif cod > 1000:
            context['feedstock_type'] = 'Municipal sludge'
        else:
            context['feedstock_type'] = 'Low-strength wastewater'

        # Project name
        context['project_name'] = f"AD_{int(Q)}_m3d_{int(cod)}_COD"
        context['reactor_type'] = 'CSTR'

        # === ADM1 State ===
        context['adm1_state'] = adm1_state
        context['validation'] = adm1_state.get('validation', {})

        # === Heuristic Config (Sizing) ===
        digester = heuristic_config.get('digester', {})
        context['volume_m3'] = digester.get('liquid_volume_m3', digester.get('total_volume_m3', 0))
        context['diameter_m'] = digester.get('diameter_m', 0)
        context['height_m'] = digester.get('height_m', 0)
        context['hd_ratio'] = digester.get('height_to_diameter_ratio', 1.0)
        context['freeboard_m'] = heuristic_config.get('operating_conditions', {}).get('vapor_headspace_fraction', 0.1) * context['height_m']
        context['n_tanks'] = digester.get('n_tanks', 1)

        # Design parameters
        context['srt_days'] = digester.get('srt_days', 20)
        context['hrt_days'] = digester.get('hrt_days', 0)
        if context['volume_m3'] > 0 and Q > 0:
            context['olr_kg_cod_m3_d'] = context['cod_load_kg_d'] / context['volume_m3']
        else:
            context['olr_kg_cod_m3_d'] = 0

        # Mixing
        mixing = heuristic_config.get('mixing', {})
        context['mixing_type'] = mixing.get('type', 'mechanical')
        context['mixing_power_kw'] = mixing.get('total_power_kw', 0)
        context['mixing_power_w_m3'] = mixing.get('target_power_w_m3', 0)

        mixing_details = mixing.get('details', {}).get('mechanical', {})
        context['impeller_type'] = mixing_details.get('impeller_type', '')
        context['impeller_diameter_m'] = mixing_details.get('impeller_diameter_m', 0)
        context['impeller_speed_rpm'] = mixing_details.get('impeller_speed_rpm', 0)
        context['power_number'] = mixing_details.get('power_number', 0)
        context['reynolds_number'] = mixing_details.get('reynolds_number', 0)
        context['flow_regime'] = mixing_details.get('flow_regime', '')

        # Pumped mixing
        pumped_details = mixing.get('details', {}).get('pumped', {})
        context['recirculation_m3_h'] = pumped_details.get('recirculation_flow_m3_h', 0)
        context['turnovers_per_hour'] = pumped_details.get('turnovers_per_hour', 0)
        context['pump_tdh_m'] = pumped_details.get('pump_tdh_m', 0)
        context['pump_power_kw'] = pumped_details.get('pump_power_kw', 0)
        context['eductor_mode'] = pumped_details.get('eductor_mode', False)
        context['entrainment_ratio'] = pumped_details.get('entrainment_ratio', 0)
        context['motive_flow_m3_h'] = pumped_details.get('motive_flow_m3_h', 0)

        # Thermal
        thermal = heuristic_config.get('thermal_analysis_request', {})
        context['feedstock_inlet_temp_c'] = thermal.get('feedstock_heating', {}).get('inlet_temp_c', 10)
        context['ambient_temp_c'] = thermal.get('tank_heat_loss', {}).get('ambient_temp_c', 0)
        context['insulation_r_value'] = thermal.get('tank_heat_loss', {}).get('insulation_R_value_si', 0)
        context['tank_heat_loss_kw'] = thermal.get('tank_heat_loss', {}).get('heat_loss_kw', 0)
        context['feedstock_heating_kw'] = thermal.get('feedstock_heating', {}).get('heating_duty_kw', 0)
        context['total_heat_duty_kw'] = context['tank_heat_loss_kw'] + context['feedstock_heating_kw']

        # Biogas handling
        biogas_config = heuristic_config.get('biogas_blower', {})
        context['biogas_production_m3_d'] = biogas_config.get('estimated_biogas_flow_m3d', 0)
        context['biogas_pressure_kpa'] = biogas_config.get('discharge_pressure_kpa', 0)
        context['blower_capacity_m3_h'] = biogas_config.get('estimated_biogas_flow_m3h', 0)
        context['blower_power_kw'] = biogas_config.get('blower_power_kw', 0)

        # === Performance ===
        context['influent'] = performance.get('influent', {})
        context['effluent'] = performance.get('effluent', {})

        biogas_perf = performance.get('biogas', {})
        context['biogas'] = {
            'total_m3_d': biogas_perf.get('total_m3_d', 0),
            'ch4_percent': biogas_perf.get('ch4_percent', 0),
            'co2_percent': biogas_perf.get('co2_percent', 0),
            'h2_percent': biogas_perf.get('h2_percent', 0),
            'h2s_ppm': biogas_perf.get('h2s_ppm', 0),
            'ch4_m3_d': biogas_perf.get('total_m3_d', 0) * biogas_perf.get('ch4_percent', 0) / 100
        }

        perf_metrics = performance.get('performance', {})
        context['cod_removal_percent'] = perf_metrics.get('cod_removal_percent', 0)
        context['tss_removal_percent'] = self._calc_removal(
            context['influent'].get('tss_mg_l', 0),
            context['effluent'].get('tss_mg_l', 0)
        )
        context['vss_removal_percent'] = self._calc_removal(
            context['influent'].get('vss_mg_l', 0),
            context['effluent'].get('vss_mg_l', 0)
        )

        context['specific_methane_yield_m3_kg_cod'] = perf_metrics.get('specific_methane_yield_m3_kg_cod', 0)
        context['specific_methane_yield_L_kg_cod'] = perf_metrics.get('specific_methane_yield_L_kg_cod', 0)
        context['net_biomass_yield_vss'] = perf_metrics.get('net_biomass_yield_kg_vss_kg_cod', 0)
        context['net_biomass_yield_tss'] = perf_metrics.get('net_biomass_yield_kg_tss_kg_cod', 0)

        # Yield efficiency
        theoretical_ch4 = 0.35  # m3 CH4/kg COD at STP
        if theoretical_ch4 > 0:
            context['yield_efficiency_percent'] = (context['specific_methane_yield_m3_kg_cod'] / theoretical_ch4) * 100
        else:
            context['yield_efficiency_percent'] = 0

        # Process stability indicators
        eff_ph = context['effluent'].get('pH', context['effluent'].get('ph', 7.0))
        context['effluent_ph'] = eff_ph
        context['ph_status'] = 'pass' if 6.8 <= eff_ph <= 7.4 else 'fail'

        context['vfa_alk_ratio'] = context['effluent'].get('vfa_alk_ratio', 0)
        context['vfa_alk_status'] = 'pass' if context['vfa_alk_ratio'] < 0.4 else 'fail'
        context['vfa_status'] = 'pass' if context['effluent'].get('vfa_mg_l', 0) < 500 else 'fail'

        # === Inhibition ===
        context['overall_methanogen_health_percent'] = inhibition.get('overall_methanogen_health_percent', 100)
        context['limiting_factors'] = inhibition.get('limiting_factors', [])

        ph_inhib = inhibition.get('pH_inhibition', {})
        context['ph_inhibition'] = {
            'acetoclastic_percent': ph_inhib.get('acetoclastic_percent', 0),
            'hydrogenotrophic_percent': ph_inhib.get('hydrogenotrophic_percent', 0)
        }
        context['acetoclastic_health_percent'] = 100 - ph_inhib.get('acetoclastic_percent', 0)
        context['hydrogenotrophic_health_percent'] = 100 - ph_inhib.get('hydrogenotrophic_percent', 0)

        context['ammonia_inhibition'] = inhibition.get('ammonia_inhibition', {})
        context['hydrogen_inhibition'] = inhibition.get('hydrogen_inhibition', {})
        context['h2s_inhibition'] = inhibition.get('h2s_inhibition', {})

        # === Precipitation ===
        context['total_precipitation_kg_d'] = precipitation.get('total_precipitation_rate_kg_d', 0)
        context['phosphorus_precipitated_kg_d'] = precipitation.get('phosphorus_precipitated_kg_d', 0)
        context['sulfur_precipitated_kg_d'] = precipitation.get('sulfur_precipitated_kg_d', 0)
        context['minerals'] = precipitation.get('minerals', {})
        context['dissolved'] = precipitation.get('dissolved_concentrations', {})

        # Chemical dosing (if present)
        context['chemical_dosing'] = heuristic_config.get('chemical_dosing', {})

        # === Summary Assessment ===
        context['critical_issues'] = []
        context['warnings'] = []
        context['recommendations'] = []

        # Check for critical issues
        if eff_ph < 6.0:
            context['critical_issues'].append(f"Effluent pH critically low ({eff_ph:.2f})")
        if context['effluent'].get('vfa_mg_l', 0) > 1000:
            context['critical_issues'].append(f"VFA accumulation critical ({context['effluent'].get('vfa_mg_l', 0):.0f} mg/L)")
        if context['overall_methanogen_health_percent'] < 50:
            context['critical_issues'].append(f"Methanogen health critically low ({context['overall_methanogen_health_percent']:.0f}%)")

        # Check for warnings
        if context['biogas'].get('ch4_percent', 0) < 50:
            context['warnings'].append(f"Low methane content ({context['biogas'].get('ch4_percent', 0):.1f}%)")
        if context['biogas'].get('h2s_ppm', 0) > 200:
            context['warnings'].append(f"High H₂S in biogas ({context['biogas'].get('h2s_ppm', 0):.0f} ppm)")
        if context['vfa_alk_ratio'] > 0.3:
            context['warnings'].append(f"Elevated VFA/Alkalinity ratio ({context['vfa_alk_ratio']:.3f})")

        # Recommendations
        if context['h2s_inhibition'].get('h2s_concentration_mg_l', 0) > 100:
            context['recommendations'].append("Consider FeCl₃ dosing for sulfide control")
        if context['ammonia_inhibition'].get('acetoclastic_percent', 0) > 20:
            context['recommendations'].append("Consider pH reduction or co-digestion to reduce ammonia inhibition")

        return context

    def _calc_removal(self, influent: float, effluent: float) -> float:
        """Calculate removal efficiency percentage."""
        if influent > 0:
            return ((influent - effluent) / influent) * 100
        return 0

    def _generate_markdown(self, context: Dict) -> str:
        """Generate Markdown content from template."""
        try:
            template = self.env.get_template('base_report.md.j2')
        except Exception as e:
            raise RuntimeError(f"Failed to load base_report.md.j2: {e}")

        try:
            # Add macros to context
            macros_template = self.env.get_template('macros/table.md.j2')
            context['macros'] = macros_template.module
        except Exception as e:
            raise RuntimeError(f"Failed to load macros/table.md.j2: {e}")

        try:
            markdown = template.render(**context)
        except Exception as e:
            import traceback
            tb = traceback.format_exc()
            raise RuntimeError(f"Template rendering failed:\n{tb}")

        return markdown


def generate_markdown_report(job_id: Optional[str] = None) -> Dict[str, str]:
    """Generate markdown report from current design state.

    Args:
        job_id: Optional job ID to load results from specific job directory

    Returns:
        Dict with path to generated report file
    """
    builder = MarkdownReportBuilder()
    result = builder.generate(job_id=job_id)
    print(f"Generated markdown report: {result['markdown']}")
    return result


if __name__ == "__main__":
    import sys
    job_id = sys.argv[1] if len(sys.argv) > 1 else None
    generate_markdown_report(job_id)
