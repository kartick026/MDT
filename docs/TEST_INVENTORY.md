# Test case inventory — 23 October 2026

Named automated checks: **400 total**. Backend: **355 passed** on 22 October (112.18s, including PostgreSQL/Neo4j); its source hashes remain unchanged. On 23 October, **20 targeted backend cases** were rerun and passed (included in the 355, not additional cases). Current client suites: **19 frontend, 7 shared client, 10 browser extension, 9 VS Code unit**, all rerun on 23 October. These counts do not measure predictive accuracy.

See [latest fixes and release gates](ALPHA_COMPLETION_2026-10-23.md), [test/bug history](TEST_AND_BUG_LOG.md) and the [current per-check CSV](benchmarks/test-inventory-2026-10-23.csv).

## Backend Python — 355

### tests/test_api_integration.py — 7

- `test_health_endpoint` — passed in the recorded full run.
- `test_services_list_endpoint` — passed in the recorded full run.
- `test_services_graph_endpoint` — passed in the recorded full run.
- `test_analysis_history_endpoint` — passed in the recorded full run.
- `test_registry_dependencies_endpoint` — passed in the recorded full run.
- `test_registry_file_mappings_endpoint` — passed in the recorded full run.
- `test_invalid_service_creation_rejected` — passed in the recorded full run.

### tests/test_api_type_safety.py — 8

- `test_analysis_request_validation` — passed in the recorded full run.
- `test_common_schemas` — passed in the recorded full run.
- `test_services_api_response_contract` — passed in the recorded full run.
- `test_services_graph_api_response_contract` — passed in the recorded full run.
- `test_registry_add_service_contract` — passed in the recorded full run.
- `test_analyze_empty_payload_rejected` — passed in the recorded full run.
- `test_analysis_rejects_repository_that_does_not_own_active_architecture` — passed in the recorded full run.
- `test_graph_uses_registry_snapshot_for_nodes_and_edges` — passed in the recorded full run.

### tests/test_audit_and_parity.py — 24

- `WhatIfScoringRegressionTests::test_after_score_proportional_reduction_when_saturated` — passed in the recorded full run.
- `WhatIfScoringRegressionTests::test_after_score_when_both_before_and_after_exceed_cap` — passed in the recorded full run.
- `WhatIfScoringRegressionTests::test_demo_fleet_what_if_preview_reductions` — passed in the recorded full run.
- `ChattyCircularExcludePairsTests::test_exclude_pairs_prevents_double_count` — passed in the recorded full run.
- `SmellDetectorOfflineParityTests::test_all_smells_detectable_under_mock_neo4j` — passed in the recorded full run.
- `DegreeBasedCoreServicesTests::test_core_services_determined_by_centrality` — passed in the recorded full run.
- `DegreeBasedCoreServicesTests::test_core_services_statistical_outlier_for_large_fleets` — passed in the recorded full run.
- `DynamicRemediationTargetTests::test_no_candidate_returns_empty` — passed in the recorded full run.
- `IsolatedServiceExclusionTests::test_baseline_is_recomputed_and_historical_findings_remain_explicit` — passed in the recorded full run.
- `IsolatedServiceExclusionTests::test_external_types_excluded_but_facade_names_have_no_exemption` — passed in the recorded full run.
- `IsolatedServiceExclusionTests::test_notification_service_detected_as_isolated_and_simulated` — passed in the recorded full run.
- `Phase9CodeAuditTests::test_impact_engine_clamping` — passed in the recorded full run.
- `Phase9CodeAuditTests::test_imported_repo_does_not_leak_demo_snapshots` — passed in the recorded full run.
- `Phase9CodeAuditTests::test_is_supported_file_includes_html_templates_and_configs` — passed in the recorded full run.
- `Phase9CodeAuditTests::test_parse_github_url_robustness` — passed in the recorded full run.
- `Phase9CodeAuditTests::test_settings_dynamic_thresholds` — passed in the recorded full run.
- `Phase9CodeAuditTests::test_simulation_negative_degradation_handling` — passed in the recorded full run.
- `MonotonicityRegressionTests::test_distinct_raw_produces_distinct_normalized` — passed in the recorded full run.
- `MonotonicityRegressionTests::test_never_attains_100` — passed in the recorded full run.
- `MonotonicityRegressionTests::test_no_collisions_in_operating_range` — passed in the recorded full run.
- `HubAndSpokeThresholdTests::test_threshold_at_large_fleet` — passed in the recorded full run.
- `HubAndSpokeThresholdTests::test_threshold_at_medium_fleet` — passed in the recorded full run.
- `HubAndSpokeThresholdTests::test_threshold_at_small_fleet` — passed in the recorded full run.
- `HubAndSpokeThresholdTests::test_threshold_never_exceeds_85_percent` — passed in the recorded full run.

### tests/test_auth.py — 18

- `test_password_hashing_and_verification` — passed in the recorded full run.
- `test_jwt_create_and_decode` — passed in the recorded full run.
- `test_expired_jwt_rejection` — passed in the recorded full run.
- `test_invalid_jwt_tampering_rejection` — passed in the recorded full run.
- `test_authenticate_user` — passed in the recorded full run.
- `test_api_login_json_success` — passed in the recorded full run.
- `test_api_login_json_invalid_credentials` — passed in the recorded full run.
- `test_viewer_signup_and_login` — passed in the recorded full run.
- `test_signup_rejects_duplicate_username` — passed in the recorded full run.
- `test_api_login_oauth2_form` — passed in the recorded full run.
- `test_api_me_authenticated` — passed in the recorded full run.
- `test_api_me_unauthenticated` — passed in the recorded full run.
- `test_api_refresh_token` — passed in the recorded full run.
- `test_protected_registry_endpoint_unauthenticated` — passed in the recorded full run.
- `test_protected_registry_endpoint_authenticated` — passed in the recorded full run.
- `test_viewer_cannot_mutate_registry` — passed in the recorded full run.
- `test_production_rejects_insecure_or_missing_secrets` — passed in the recorded full run.
- `test_login_rate_limiting_enforced` — passed in the recorded full run.

### tests/test_change_extraction_regressions.py — 14

- `test_two_commit_range_reads_both_full_snapshots` — passed in the recorded full run.
- `test_rename_and_deletion_preserve_old_source` — passed in the recorded full run.
- `test_unknown_sha_fails_instead_of_safe_empty_analysis` — passed in the recorded full run.
- `test_submitted_changed_endpoint_is_not_remote_head` — passed in the recorded full run.
- `test_oversized_and_invalid_python_are_explicitly_partial` — passed in the recorded full run.
- `test_api_non_entrypoint_reads_old_and_new_source` — passed in the recorded full run.
- `test_onboarding_reads_nested_router_and_preserves_file_evidence` — passed in the recorded full run.
- `test_core_service_counts_distinct_callers_not_routes` — passed in the recorded full run.
- `test_hook_staged_uses_index_and_working_uses_actual_worktree` — passed in the recorded full run.
- `test_pre_push_reads_supplied_full_ref_range` — passed in the recorded full run.
- `test_hook_error_blocks_unless_explicit_warn` — passed in the recorded full run.
- `test_route_removal_in_main_file_triggers_api_change_risk` — passed in the recorded full run.
- `test_scoped_impact_explanation_does_not_call_llm` — passed in the recorded full run.
- `test_http_method_change_same_path_is_contract_change` — passed in the recorded full run.

### tests/test_connection_validator_and_onboarding.py — 9

- `TestConnectionValidator::test_detect_404_and_port_mismatch` — passed in the recorded full run.
- `TestConnectionValidator::test_detect_localhost_container_networking_bug` — passed in the recorded full run.
- `TestConnectionValidator::test_extract_polyglot_routes` — passed in the recorded full run.
- `TestConnectionValidator::test_extract_routes` — passed in the recorded full run.
- `TestConnectionValidator::test_ignore_cors_whitelists_and_unknown_files` — passed in the recorded full run.
- `TestRepoOnboarder::test_infer_from_file_tree` — passed in the recorded full run.
- `TestRepoOnboarder::test_infer_service_language` — passed in the recorded full run.
- `TestRepoOnboarder::test_inference_preserves_compose_dependencies` — passed in the recorded full run.
- `TestRepoOnboarder::test_parse_compose` — passed in the recorded full run.

### tests/test_contract_context_accuracy.py — 8

- `test_job_resolves_unchanged_consumers_and_exposes_evidence` — passed in the recorded full run.
- `test_context_is_part_of_source_fingerprint` — passed in the recorded full run.
- `test_optional_response_field_is_not_claimed_backward_compatible` — passed in the recorded full run.
- `test_missing_model_source_does_not_invent_removed_contract` — passed in the recorded full run.
- `test_inherited_imported_fields_link_to_unchanged_route` — passed in the recorded full run.
- `test_transport_distinguishes_empty_file_from_missing_file` — passed in the recorded full run.
- `test_json_types_are_not_collapsed_by_python_equality[{"value":true}-{"value":1}]` — passed in the recorded full run.
- `test_json_types_are_not_collapsed_by_python_equality[{"value":1}-{"value":1.0}]` — passed in the recorded full run.

### tests/test_database_and_registry.py — 9

- `DatabaseAndRegistryTests::test_database_health_checks` — passed in the recorded full run.
- `DatabaseAndRegistryTests::test_local_demo_fleet_contains_evidence_for_every_detector` — passed in the recorded full run.
- `DatabaseAndRegistryTests::test_mock_neo4j_driver_compatibility` — passed in the recorded full run.
- `DatabaseAndRegistryTests::test_registry_in_memory_cache` — passed in the recorded full run.
- `DatabaseAndRegistryTests::test_registry_validation_invalid_name` — passed in the recorded full run.
- `DatabaseAndRegistryTests::test_registry_validation_invalid_port` — passed in the recorded full run.
- `DatabaseAndRegistryTests::test_registry_validation_valid_service` — passed in the recorded full run.
- `DatabaseAndRegistryTests::test_repository_key_normalizes_github_url_variants` — passed in the recorded full run.
- `DatabaseAndRegistryTests::test_service_registry_helper` — passed in the recorded full run.

### tests/test_demo_previews.py — 1

- `test_public_demo_previews_are_recomputed_from_exact_edits_without_mutation` — passed in the recorded full run.

### tests/test_dependency_graph.py — 3

- `DependencyGraphTests::test_get_dependants_from_static_map` — passed in the recorded full run.
- `DependencyGraphTests::test_infer_service_from_path` — passed in the recorded full run.
- `DependencyGraphTests::test_static_dependency_chain` — passed in the recorded full run.

### tests/test_finding_reviews.py — 5

- `test_reviews_are_owned_expiring_annotations_without_score_mutation` — passed in the recorded full run.
- `test_review_validation[override0]` — passed in the recorded full run.
- `test_review_validation[override1]` — passed in the recorded full run.
- `test_review_validation[override2]` — passed in the recorded full run.
- `test_review_validation[override3]` — passed in the recorded full run.

### tests/test_git_analyzer.py — 8

- `ASTAnalyzerTests::test_javascript_regex` — passed in the recorded full run.
- `ASTAnalyzerTests::test_python_ast` — passed in the recorded full run.
- `CommitResolutionTests::test_resolve_40_char_sha` — passed in the recorded full run.
- `CommitResolutionTests::test_resolve_empty_and_whitespace_ref` — passed in the recorded full run.
- `CommitResolutionTests::test_resolve_relative_ref_traversal` — passed in the recorded full run.
- `CommitResolutionTests::test_resolve_short_sha_via_github_api` — passed in the recorded full run.
- `RepoKeyNormalizationTests::test_normalize_repository_key_variants` — passed in the recorded full run.
- `DiffBaseAndCloneTests::test_explicit_commit_does_not_merge_base_with_main` — passed in the recorded full run.

### tests/test_history_and_drift.py — 10

- `test_history_pagination_filters_literal_search_and_summary_privacy` — passed in the recorded full run.
- `test_history_snapshot_and_baseline_endpoints_enforce_owner` — passed in the recorded full run.
- `test_initial_snapshot_baseline_and_same_capture_are_truthful` — passed in the recorded full run.
- `test_seeded_demo_snapshot_discovery_and_legacy_baseline_compatibility` — passed in the recorded full run.
- `test_retention_preserves_pinned_baseline_and_current_capture` — passed in the recorded full run.
- `test_archived_snapshot_is_immutable_and_separate_from_current_project` — passed in the recorded full run.
- `test_contract_only_changes_affect_snapshot_version_but_source_lines_do_not` — passed in the recorded full run.
- `test_drift_reports_real_captures_contract_edits_edges_and_score_direction` — passed in the recorded full run.
- `test_baseline_and_finish_racing_deletion_cannot_recreate_project_records` — passed in the recorded full run.
- `test_reimport_uses_requested_revision_and_persists_resolved_capture` — passed in the recorded full run.

### tests/test_hook_v1.py — 14

- `test_hook_uses_project_owned_async_job_with_real_http` — passed in the recorded full run.
- `test_mismatched_repository_never_uploads_source` — passed in the recorded full run.
- `test_not_ready_project_blocks_before_submission` — passed in the recorded full run.
- `test_timeout_cancels_queued_job` — passed in the recorded full run.
- `test_interruption_cancels_job` — passed in the recorded full run.
- `test_redirect_never_forwards_token` — passed in the recorded full run.
- `test_auth_error_gives_action_without_echoing_error_body` — passed in the recorded full run.
- `test_unsafe_server_urls_block[http://remote.example]` — passed in the recorded full run.
- `test_unsafe_server_urls_block[https://user:pass@example.com]` — passed in the recorded full run.
- `test_unsafe_server_urls_block[https://example.com/?token=secret]` — passed in the recorded full run.
- `test_unsafe_server_urls_block[https://example.com/#secret]` — passed in the recorded full run.
- `test_configuration_required_without_silent_legacy_fallback` — passed in the recorded full run.
- `test_legacy_is_explicit_opt_in` — passed in the recorded full run.
- `test_partial_result_never_approves_change` — passed in the recorded full run.

### tests/test_impact_engine.py — 7

- `ImpactEngineTests::test_compute_base_risk` — passed in the recorded full run.
- `ImpactEngineTests::test_compute_confidence` — passed in the recorded full run.
- `ImpactEngineTests::test_get_severity` — passed in the recorded full run.
- `ImpactEngineTests::test_has_api_changes` — passed in the recorded full run.
- `ImpactEngineTests::test_has_config_changes` — passed in the recorded full run.
- `ImpactEngineTests::test_has_core_service_impact` — passed in the recorded full run.
- `ImpactEngineTests::test_has_schema_changes` — passed in the recorded full run.

### tests/test_import_evidence_values.py — 6

- `test_compose_missing_port_and_startup_order_do_not_invent_http_endpoint` — passed in the recorded full run.
- `test_database_resources_and_named_application_services_are_not_discarded` — passed in the recorded full run.
- `test_failed_import_status_survives_reopening_directory` — passed in the recorded full run.
- `test_manifest_declarations_prevent_duplicate_aliases_and_build_template_services` — passed in the recorded full run.
- `test_unassessed_graph_node_never_receives_fake_zero_or_ninety` — passed in the recorded full run.
- `test_service_list_preserves_missing_and_measured_zero_against_stale_graph` — passed in the recorded full run.

### tests/test_llm_explainer.py — 6

- `LLMExplainerTests::test_fallback_explanation` — passed in the recorded full run.
- `LLMExplainerTests::test_fallback_proposals_are_grouped_by_finding_not_guessed_edit_count` — passed in the recorded full run.
- `LLMExplainerTests::test_fallback_remediation` — passed in the recorded full run.
- `LLMExplainerTests::test_hosted_profile_never_invokes_model_provider` — passed in the recorded full run.
- `LLMExplainerTests::test_owned_project_disables_even_a_preexisting_provider_client` — passed in the recorded full run.
- `LLMExplainerTests::test_severity_label` — passed in the recorded full run.

### tests/test_observability.py — 4

- `test_request_id_and_latency_headers` — passed in the recorded full run.
- `test_custom_request_id_propagation` — passed in the recorded full run.
- `test_detailed_health_observability` — passed in the recorded full run.
- `test_json_log_formatter` — passed in the recorded full run.

### tests/test_preview_neo4j_integration.py — 3

- `test_live_transaction_matches_copy_and_preserves_entire_graph` — passed in the recorded full run.
- `test_real_transaction_rolls_back_when_evaluation_raises` — passed in the recorded full run.
- `test_concurrent_real_previews_do_not_leak_each_others_changes` — passed in the recorded full run.

### tests/test_project_policies.py — 2

- `test_constraints_preserve_explicit_unresolved_evidence_and_scores` — passed in the recorded full run.
- `test_project_rules_owned_validated_and_copied_into_job` — passed in the recorded full run.

### tests/test_projects_jobs.py — 9

- `test_public_demo_and_protected_data` — passed in the recorded full run.
- `test_owner_isolation_and_live_role_check` — passed in the recorded full run.
- `test_logout_and_refresh_revoke_old_tokens` — passed in the recorded full run.
- `test_patch_job_real_pipeline_persists_and_preview_is_immutable` — passed in the recorded full run.
- `test_leases_restart_cancellation_and_fencing` — passed in the recorded full run.
- `test_quota_delete_and_bounded_input` — passed in the recorded full run.
- `test_snapshot_context_does_not_touch_global_registry` — passed in the recorded full run.
- `test_hosted_configuration_requires_durable_secure_setup` — passed in the recorded full run.
- `test_password_byte_limit` — passed in the recorded full run.

### tests/test_public_github_source.py — 10

- `test_archive_keeps_empty_binary_and_oversized_source_distinct` — passed in the recorded full run.
- `test_archive_rejects_path_traversal_without_extracting[../secret]` — passed in the recorded full run.
- `test_archive_rejects_path_traversal_without_extracting[root/../../secret]` — passed in the recorded full run.
- `test_archive_rejects_path_traversal_without_extracting[/absolute]` — passed in the recorded full run.
- `test_archive_rejects_path_traversal_without_extracting[x\\secret]` — passed in the recorded full run.
- `test_expanded_size_and_file_bounds_are_enforced` — passed in the recorded full run.
- `test_anonymous_quota_fallback_reuses_one_exact_archive` — passed in the recorded full run.
- `test_private_rate_limit_never_falls_back_to_public_archive` — passed in the recorded full run.
- `test_public_actual_parent_comparison_uses_sources_and_reports_limits` — passed in the recorded full run.
- `test_unchanged_oversized_blobs_are_not_reported_as_changes` — passed in the recorded full run.

### tests/test_remediation_simulator.py — 30

- `test_invalid_operations_are_rejected[payload0]` — passed in the recorded full run.
- `test_invalid_operations_are_rejected[payload1]` — passed in the recorded full run.
- `test_invalid_operations_are_rejected[payload2]` — passed in the recorded full run.
- `test_invalid_operations_are_rejected[payload3]` — passed in the recorded full run.
- `test_invalid_operations_are_rejected[payload4]` — passed in the recorded full run.
- `test_invalid_operations_are_rejected[payload5]` — passed in the recorded full run.
- `test_no_edit_recomputes_baseline_and_has_zero_change` — passed in the recorded full run.
- `test_removing_unrelated_edge_does_not_resolve_cycle_and_reports_new_isolation` — passed in the recorded full run.
- `test_adding_cycle_is_measured_as_degradation` — passed in the recorded full run.
- `test_removing_cycle_edge_preserves_functional_warning_and_live_input` — passed in the recorded full run.
- `test_gateway_name_does_not_grant_resilience_or_erase_findings` — passed in the recorded full run.
- `test_explicit_resilience_property_changes_only_supported_evidence` — passed in the recorded full run.
- `test_snapshot_version_rejects_stale_baseline` — passed in the recorded full run.
- `test_unknown_service_missing_edge_and_excessive_edits_rejected` — passed in the recorded full run.
- `test_late_validation_error_leaves_original_snapshot_unchanged` — passed in the recorded full run.
- `test_ambiguous_removal_requires_an_endpoint_selector` — passed in the recorded full run.
- `test_commit_risk_is_separate_from_measured_debt` — passed in the recorded full run.
- `test_published_normalization_and_precision[244-86.936]` — passed in the recorded full run.
- `test_published_normalization_and_precision[214-85.372]` — passed in the recorded full run.
- `test_published_normalization_and_precision[184-83.384]` — passed in the recorded full run.
- `test_published_normalization_and_precision[154-80.769]` — passed in the recorded full run.
- `test_published_normalization_and_precision[124-77.178]` — passed in the recorded full run.
- `test_published_normalization_and_precision[216-85.488]` — passed in the recorded full run.
- `test_published_normalization_and_precision[144-79.705]` — passed in the recorded full run.
- `test_published_normalization_and_precision[75-67.164]` — passed in the recorded full run.
- `test_preview_json_preserves_three_decimal_values` — passed in the recorded full run.
- `test_all_weights_and_zero` — passed in the recorded full run.
- `test_generated_shared_database_plan_keeps_a_path_to_storage` — passed in the recorded full run.
- `test_live_transaction_rolls_back_after_failure_in_detector` — passed in the recorded full run.
- `test_transaction_mode_requires_live_connection` — passed in the recorded full run.

### tests/test_repo_discovery_accuracy.py — 11

- `test_shared_compose_context_maps_nested_dockerfile_and_repairs_declared_directory` — passed in the recorded full run.
- `test_compose_source_context_never_collapses_parent_or_remote_path_into_repo` — passed in the recorded full run.
- `test_large_frontend_does_not_starve_backend_source` — passed in the recorded full run.
- `test_empty_module_counts_as_read_and_missing_source_is_not_infra` — passed in the recorded full run.
- `test_libraries_and_tutorials_do_not_establish_deployment[tree0]` — passed in the recorded full run.
- `test_libraries_and_tutorials_do_not_establish_deployment[tree1]` — passed in the recorded full run.
- `test_libraries_and_tutorials_do_not_establish_deployment[tree2]` — passed in the recorded full run.
- `test_directory_names_do_not_invent_frontend_backend_edge` — passed in the recorded full run.
- `test_vite_application_discovered_but_email_template_package_excluded` — passed in the recorded full run.
- `test_kubernetes_services_use_selectors_and_only_explicit_endpoint_references` — passed in the recorded full run.
- `test_kubernetes_manifest_budget_and_templates_are_explicit` — passed in the recorded full run.

### tests/test_retrieval.py — 7

- `RetrievalEngineTests::test_chunk_content` — passed in the recorded full run.
- `RetrievalEngineTests::test_compute_risk_modifier` — passed in the recorded full run.
- `RetrievalEngineTests::test_purge_collection_graceful_handling` — passed in the recorded full run.
- `RetrievalEngineTests::test_tfidf_embed_produces_normalized_vectors` — passed in the recorded full run.
- `VersionedRetrievalTests::test_chronology_project_filters_and_lexical_zero_modifier` — passed in the recorded full run.
- `VersionedRetrievalTests::test_disabled_retrieval_never_calls_embedding_provider` — passed in the recorded full run.
- `VersionedRetrievalTests::test_revisions_and_embedding_dimensions_do_not_overwrite_or_purge_history` — passed in the recorded full run.

### tests/test_risk_evidence.py — 4

- `test_equivalent_core_service_changes_have_zero_risk_even_at_depth` — passed in the recorded full run.
- `test_breaking_route_scores_above_additive_route` — passed in the recorded full run.
- `test_confidence_tracks_missing_source_and_mapping_not_graph_depth` — passed in the recorded full run.
- `test_partial_source_cannot_look_like_confirmed_safe_noop` — passed in the recorded full run.

### tests/test_scoring_accuracy_controls.py — 21

- `test_comments_and_formatting_do_not_create_risk[service/api/controller.py-def load():\n    return "# significant"\n-# comment\ndef load():\n    return "# significant"  # comment\n]` — passed in the recorded full run.
- `test_comments_and_formatting_do_not_create_risk[service/api/controller.ts-export const value = "http://example.invalid";\n-// app.delete("/fake", handler)\nexport const value = "http://example.invalid"; /* comment */\n]` — passed in the recorded full run.
- `test_comments_and_formatting_do_not_create_risk[service/config.py-TIMEOUT = 30\n-TIMEOUT = 30  # only explanatory\n]` — passed in the recorded full run.
- `test_comments_and_formatting_do_not_create_risk[docker-compose.yaml-services:\n  api:\n    image: acme/api:1\n-# configuration explanation\nservices:\n  api:\n    image: acme/api:1 # same image\n]` — passed in the recorded full run.
- `test_comments_and_formatting_do_not_create_risk[service/settings.json-{"timeout":30,"url":"http://example.invalid"}-{\n  "url": "http://example.invalid",\n  "timeout": 30\n}]` — passed in the recorded full run.
- `test_comments_and_formatting_do_not_create_risk[service/pyproject.toml-[settings]\ntimeout = 30\n-# explanatory\n[settings]\ntimeout = 30 # unchanged\n]` — passed in the recorded full run.
- `test_runtime_edits_remain_changes_without_inventing_contract_changes[api.py-@app.get("/value")\ndef value():\n    return 1\n-@app.get("/value")\ndef value():\n    return 2\n]` — passed in the recorded full run.
- `test_runtime_edits_remain_changes_without_inventing_contract_changes[routes.js-app.get("/value", (req, res) => res.send("one"));-app.get("/value", (req, res) => res.send("two"));]` — passed in the recorded full run.
- `test_runtime_edits_remain_changes_without_inventing_contract_changes[routes.ts-const url = "http://one.invalid";-const url = "http://two.invalid";]` — passed in the recorded full run.
- `test_deployment_value_edit_is_not_suppressed_as_comment` — passed in the recorded full run.
- `test_missing_source_is_unknown_not_equivalent` — passed in the recorded full run.
- `test_invalid_source_cannot_be_a_safe_noop` — passed in the recorded full run.
- `test_imported_request_model_compatibility_is_not_just_a_filename[from pydantic import BaseModel\nclass CreateWidget(BaseModel):\n    label: str\n    note: str | None = None\n-additive]` — passed in the recorded full run.
- `test_imported_request_model_compatibility_is_not_just_a_filename[from pydantic import BaseModel\nclass CreateWidget(BaseModel):\n    label: str\n    quantity: int\n-breaking]` — passed in the recorded full run.
- `test_imported_request_model_compatibility_is_not_just_a_filename[from pydantic import BaseModel\nclass CreateWidget(BaseModel):\n    label: int\n-breaking]` — passed in the recorded full run.
- `test_imported_request_model_compatibility_is_not_just_a_filename[from pydantic import BaseModel\nclass CreateWidget(BaseModel):\n    pass\n-breaking]` — passed in the recorded full run.
- `test_model_requiredness_relaxation_is_additive` — passed in the recorded full run.
- `test_model_requiredness_tightening_is_breaking` — passed in the recorded full run.
- `test_unrelated_helper_class_is_not_invented_as_public_schema` — passed in the recorded full run.
- `test_literal_route_addition_and_removal_are_distinguished` — passed in the recorded full run.
- `test_type_widening_is_not_automatically_declared_compatible` — passed in the recorded full run.

### tests/test_smell_detector.py — 33

- `test_simple_cycles_are_canonical_and_self_loops_are_evidence` — passed in the recorded full run.
- `test_parallel_endpoints_do_not_duplicate_a_cycle` — passed in the recorded full run.
- `test_two_node_cycle_is_not_double_counted_as_chatter` — passed in the recorded full run.
- `test_bottleneck_counts_distinct_callers` — passed in the recorded full run.
- `test_parallel_endpoint_edges_do_not_inflate_coupling` — passed in the recorded full run.
- `test_high_coupling_is_measured_from_distinct_targets` — passed in the recorded full run.
- `test_named_facades_gateways_and_brokers_are_not_implicitly_exempt` — passed in the recorded full run.
- `test_unknown_dependency_target_is_external_not_an_extra_runnable_service` — passed in the recorded full run.
- `test_shared_database_uses_explicit_resource_type_not_name` — passed in the recorded full run.
- `test_database_typed_edges_upgrade_legacy_resource_metadata` — passed in the recorded full run.
- `test_circuit_breaker_evidence_must_be_explicit` — passed in the recorded full run.
- `test_hub_threshold_rejects_symmetric_mesh` — passed in the recorded full run.
- `test_hub_threshold_detects_star` — passed in the recorded full run.
- `test_historical_growth_requires_two_distinct_actual_snapshots` — passed in the recorded full run.
- `test_api_history_detects_removed_endpoint_but_ignores_unchanged` — passed in the recorded full run.
- `test_foreign_history_does_not_enter_a_project` — passed in the recorded full run.
- `test_renaming_preserves_all_counts_and_scores` — passed in the recorded full run.
- `test_circuit_breaker_threshold[2-2]` — passed in the recorded full run.
- `test_circuit_breaker_threshold[3-2]` — passed in the recorded full run.
- `test_circuit_breaker_threshold[5-3]` — passed in the recorded full run.
- `test_circuit_breaker_threshold[9-3]` — passed in the recorded full run.
- `test_circuit_breaker_threshold[10-4]` — passed in the recorded full run.
- `test_circuit_breaker_threshold[25-5]` — passed in the recorded full run.
- `test_distribution_modulates_circuit_breaker_threshold` — passed in the recorded full run.
- `test_hub_threshold[1-0]` — passed in the recorded full run.
- `test_hub_threshold[2-0]` — passed in the recorded full run.
- `test_hub_threshold[3-2]` — passed in the recorded full run.
- `test_hub_threshold[4-2]` — passed in the recorded full run.
- `test_hub_threshold[5-3]` — passed in the recorded full run.
- `test_hub_threshold[10-7]` — passed in the recorded full run.
- `test_hub_threshold[200-170]` — passed in the recorded full run.
- `test_detector_adapter_uses_same_snapshot_with_no_graph_mutations` — passed in the recorded full run.
- `test_snapshot_is_owned_and_mapping_changes_invalidate_its_version` — passed in the recorded full run.

### tests/test_source_parser_and_cache.py — 12

- `test_typescript_syntax_ignores_comments_strings_and_reads_real_declarations` — passed in the recorded full run.
- `test_tsx_and_single_argument_arrow_are_parsed` — passed in the recorded full run.
- `test_invalid_javascript_and_dynamic_routes_are_explicitly_partial` — passed in the recorded full run.
- `test_python_same_path_contract_changes_include_model_fields_and_requiredness` — passed in the recorded full run.
- `test_contracts_ignore_line_comments_and_implementation_only_changes` — passed in the recorded full run.
- `test_fastapi_field_and_query_required_flags_and_multiple_methods` — passed in the recorded full run.
- `test_cache_reuses_only_exact_full_shas_not_moving_refs` — passed in the recorded full run.
- `test_cache_is_isolated_per_client_credentials_repo_and_path` — passed in the recorded full run.
- `test_cache_byte_bound_evicts_least_recently_used` — passed in the recorded full run.
- `test_rate_limit_stops_network_retries_and_retains_safe_evidence` — passed in the recorded full run.
- `test_forbidden_is_not_confused_with_rate_limit_or_cached` — passed in the recorded full run.
- `test_onboarding_retains_parser_and_rate_limit_coverage` — passed in the recorded full run.

### tests/test_store_postgres.py — 9

- `test_postgres_reopen_owner_isolation_and_transaction_rollback` — passed in the recorded full run.
- `test_postgres_concurrent_account_and_project_creation` — passed in the recorded full run.
- `test_postgres_concurrent_enqueue_idempotency_and_quota` — passed in the recorded full run.
- `test_postgres_skip_locked_claims_and_terminal_source_erasure` — passed in the recorded full run.
- `test_postgres_restart_fences_stale_and_cancelled_imports` — passed in the recorded full run.
- `test_postgres_exhausted_retries_and_retention` — passed in the recorded full run.
- `test_postgres_project_delete_keeps_daily_quota_and_other_owner` — passed in the recorded full run.
- `test_postgres_history_projection_search_and_snapshot_baseline` — passed in the recorded full run.
- `test_postgres_baseline_delete_and_finish_leave_no_orphaned_capture` — passed in the recorded full run.

### tests/test_store_security.py — 20

- `test_record_write_cannot_overwrite_another_owner` — passed in the recorded full run.
- `test_account_creation_is_insert_only_under_concurrent_requests` — passed in the recorded full run.
- `test_project_quota_is_atomic_across_concurrent_creates` — passed in the recorded full run.
- `test_deleting_project_does_not_reset_daily_usage_quota` — passed in the recorded full run.
- `test_idempotency_returns_same_job_only_for_same_input` — passed in the recorded full run.
- `test_idempotency_mismatch_is_http_409` — passed in the recorded full run.
- `test_owner_cannot_read_or_cancel_other_users_job` — passed in the recorded full run.
- `test_owned_job_submission_requires_an_existing_owned_project` — passed in the recorded full run.
- `test_api_submission_racing_project_deletion_does_not_recreate_source` — passed in the recorded full run.
- `test_concurrent_delete_and_enqueue_leave_no_orphaned_job` — passed in the recorded full run.
- `test_api_deletion_after_enqueue_returns_not_found_instead_of_server_error` — passed in the recorded full run.
- `test_expired_lease_cannot_publish_after_job_is_reclaimed` — passed in the recorded full run.
- `test_revocation_retention_uses_expiry_not_record_age` — passed in the recorded full run.
- `test_incomplete_or_ambiguous_patch_source_is_rejected[payload0]` — passed in the recorded full run.
- `test_incomplete_or_ambiguous_patch_source_is_rejected[payload1]` — passed in the recorded full run.
- `test_incomplete_or_ambiguous_patch_source_is_rejected[payload2]` — passed in the recorded full run.
- `test_incomplete_or_ambiguous_patch_source_is_rejected[payload3]` — passed in the recorded full run.
- `test_incomplete_or_ambiguous_patch_source_is_rejected[payload4]` — passed in the recorded full run.
- `test_explicit_addition_and_deletion_source_sides_are_valid` — passed in the recorded full run.
- `test_path_mapping_uses_longest_directory_boundary` — passed in the recorded full run.

### tests/test_webhook_security.py — 4

- `test_webhook_ping_with_valid_signature` — passed in the recorded full run.
- `test_webhook_invalid_signature_rejected` — passed in the recorded full run.
- `test_webhook_rate_limiting_enforced` — passed in the recorded full run.
- `test_webhook_test_endpoint` — passed in the recorded full run.

### tests/test_repository_evidence_regressions.py — 19

- `test_declarations_do_not_prove_chatter_missing_resilience_or_shared_database` — passed in the recorded full run.
- `test_imported_missing_resilience_is_unknown_even_with_actual_static_calls` — passed in the recorded full run.
- `test_callback_configuration_cycle_is_not_a_synchronous_call_cycle` — passed in the recorded full run.
- `test_zero_observed_debt_retains_insufficient_communication_evidence` — passed in the recorded full run.
- `test_source_calls_preserve_parallel_paths_and_startup_type` — passed in the recorded full run.
- `test_compose_port_forms_do_not_invent_host_port[ports0-expose0-expected0]` — passed in the recorded full run.
- `test_compose_port_forms_do_not_invent_host_port[ports1-expose1-expected1]` — passed in the recorded full run.
- `test_compose_port_forms_do_not_invent_host_port[ports2-expose2-expected2]` — passed in the recorded full run.
- `test_compose_port_forms_do_not_invent_host_port[ports3-expose3-expected3]` — passed in the recorded full run.
- `test_compose_port_forms_do_not_invent_host_port[ports4-expose4-expected4]` — passed in the recorded full run.
- `test_compose_port_forms_do_not_invent_host_port[ports5-expose5-expected5]` — passed in the recorded full run.
- `test_literal_configuration_references_are_sanitized_and_unresolved_values_ignored` — passed in the recorded full run.
- `test_recorded_compose_defaults_resolve_references_without_using_host_environment` — passed in the recorded full run.
- `test_compose_env_file_precedence_passthrough_and_bounded_safe_reads` — passed in the recorded full run.
- `test_library_with_same_name_as_infrastructure_is_not_source_ownership` — passed in the recorded full run.
- `test_project_depth_is_distance_not_fanout_or_disabled_shared_database` — passed in the recorded full run.
- `test_canonical_kubernetes_manifest_precedes_optional_monitoring_budget` — passed in the recorded full run.
- `test_aspire_literal_topology_is_generic_and_does_not_execute_helpers` — passed in the recorded full run.
- `test_aspire_ambiguous_apphosts_abstain` — passed in the recorded full run.

## Frontend — 19

- debt precision survives formatting and export — passed.
- counterfactual labels reflect the actual score direction and API edit fields — passed.
- historical comparisons keep missing measurements distinct from measured zero — passed.
- missing and partial architecture scores never produce a reassuring low-debt assessment — passed.
- import results retain findings and correct project/job destinations without inventing commit risk — passed.
- missing evidence never becomes a semantic or complete claim — passed.
- links preserve project and job without allowing unknown tabs — passed.
- shareable reports escape repository-controlled markup and preserve score precision — passed.
- logout clears only MDT session records — passed.
- in-flight old sessions cannot revoke or clear a renewed session — passed.
- renaming services leaves geometry unchanged, including reverse edges, loops and parallel relations — passed.
- 60 cyclic, disconnected and long-name nodes have obstacle-avoiding routes — passed.
- empty, isolated and dangling-input graphs stay finite without fabricated relations — passed.
- fit uses both viewport dimensions and never upscales a small graph — passed.
- saved live repository graphs and demo keep nodes, routes and labels separate in both directions — passed.
- updated repository topologies remain separated in connection and individual-relation views — passed.
- connection view preserves endpoint, method and provenance records without changing the snapshot — passed.
- connection grouping retains self loops, unresolved evidence, broken records and arbitrary names — passed.
- completed graph layouts reuse geometry and evict the least recently used entry — passed.

## Shared client — 7

- remote credentials require HTTPS and cannot be put into URLs — passed.
- expired sessions and HTML endpoints explain the next action — passed.
- job polling forwards cancellation to the request — passed.
- GitHub contexts preserve real comparison and PR identity — passed.
- requests carry auth and idempotency without allowing redirects — passed.
- server errors remain actionable and precise scores survive summaries — passed.
- client summaries preserve insufficient architecture evidence and distinguish missing scores from zero — passed.

## Browser extension — 10

- browser package has no passive browsing or remote script access — passed.
- late popup polling response cannot restore results after disconnect — passed.
- denied API permission never sends the entered credential to the worker — passed.
- service worker restart resumes the session job without persisting token locally — passed.
- project mismatch does not submit an analysis — passed.
- connection snapshots ignore conflicting local defaults and reject stale popup requests — passed.
- late submission cancels on its original server without restoring a job — passed.
- disconnect invalidates a connection still being validated — passed.
- reconnect during a storage write rolls back before worker restart — passed.
- legacy unbound credentials require reconnect instead of guessing their server — passed.

## VS Code unit — 9

- staged analysis reads index content even when the working file differs — passed.
- paths cannot escape the selected repository — passed.
- tree presents canonical smells and exact source provenance without guessed lines — passed.
- status represents idle, active, and partial jobs without fabricated risk — passed.
- editor evidence includes the architecture assessment even without the legacy partial flag — passed.
- web bundle activates with no Node globals and sends only confirmed revision identifiers — passed.
- denied confirmation and mismatched repository never submit source or analysis — passed.
- web disconnect during submission cancels original job and keeps saved evidence cleared — passed.
- configuration change during secret lookup cannot redirect the credential — passed.
