## Code Graph: .  (504 defs, 1 routes, 1 models)

### Dependency Graph (0 edges)
(no local dependencies detected)

### Definitions (504)
| Name | Type | File:Line |
|------|------|-----------|
| `body` | class | build.py:50 |
| `App` | class | build.py:59 |
| `App` | class | build.py:60 |
| `App` | class | build.py:63 |
| `main` | fn | build.py:69 |
| `_secure_dir` | fn | src/_constants.py:8 |
| `_secure_file` | fn | src/_constants.py:12 |
| `est_tok` | fn | src/_constants.py:28 |
| `est_tok` | fn | src/_constants.py:31 |
| `C` | class | src/_constants.py:46 |
| `rl_wrap` | fn | src/_constants.py:67 |
| `vlen` | fn | src/_constants.py:75 |
| `pad` | fn | src/_constants.py:76 |
| `mask` | fn | src/_constants.py:77 |
| `parse_value` | fn | src/_constants.py:79 |
| `fmt_time` | fn | src/_constants.py:91 |
| `_dbg_exc` | fn | src/app.py:2 |
| `App` | class | src/app.py:10 |
| `__init__` | fn | src/app.py:13 |
| `_validate_config` | fn | src/app.py:41 |
| `_get_ollama_models` | fn | src/app.py:55 |
| `_run_setup` | fn | src/app.py:62 |
| `_ver_tuple` | fn | src/app.py:107 |
| `_self_update` | fn | src/app.py:115 |
| `setup_rl` | fn | src/app.py:158 |
| `completer` | fn | src/app.py:165 |
| `info` | fn | src/app.py:175 |
| `warn` | fn | src/app.py:176 |
| `err` | fn | src/app.py:177 |
| `success` | fn | src/app.py:178 |
| `print_startup_status` | fn | src/app.py:180 |
| `print_help` | fn | src/app.py:204 |
| `_attach_files` | fn | src/app.py:223 |
| `replacer` | fn | src/app.py:227 |
| `_scan_directory` | fn | src/app.py:243 |
| `_confirm_batch` | fn | src/app.py:273 |
| `_continue_fn` | fn | src/app.py:298 |
| `_stream_tool_chat` | fn | src/app.py:315 |
| `flush` | fn | src/app.py:326 |
| `_last_cid_file` | fn | src/app.py:401 |
| `_get_last_cid` | fn | src/app.py:404 |
| `_set_last_cid` | fn | src/app.py:411 |
| `_clear_last_cid` | fn | src/app.py:417 |
| `_persist_session` | fn | src/app.py:424 |
| `_ago` | fn | src/app.py:429 |
| `_activate` | fn | src/app.py:441 |
| `_maybe_resume` | fn | src/app.py:463 |
| `_count_tool_steps` | fn | src/app.py:486 |
| `_auto_continue_attempt` | fn | src/app.py:497 |
| `_handle_interruption` | fn | src/app.py:525 |
| `_continue_from_checkpoint` | fn | src/app.py:560 |
| `_chat` | fn | src/app.py:578 |
| `_make_strategy` | fn | src/app.py:649 |
| `_show_strategy` | fn | src/app.py:674 |
| `_compact_conversation` | fn | src/app.py:681 |
| `_match_price` | fn | src/app.py:701 |
| `_read_stdin` | fn | src/app.py:711 |
| `_override_model` | fn | src/app.py:721 |
| `_strip_code_fence` | fn | src/app.py:730 |
| `_ask` | fn | src/app.py:738 |
| `oneshot` | fn | src/app.py:775 |
| `json_oneshot` | fn | src/app.py:783 |
| `command_gen` | fn | src/app.py:791 |
| `_execute_command` | fn | src/app.py:839 |
| `main_loop` | fn | src/app.py:854 |
| `BackendError` | class | src/backends.py:2 |
| `__init__` | fn | src/backends.py:5 |
| `Backend` | class | src/backends.py:9 |
| `__init__` | fn | src/backends.py:10 |
| `_api_key` | fn | src/backends.py:12 |
| `_req` | fn | src/backends.py:19 |
| `_sse_lines` | fn | src/backends.py:50 |
| `_transient` | fn | src/backends.py:70 |
| `_with_retry` | fn | src/backends.py:78 |
| `_has_payload` | fn | src/backends.py:92 |
| `_stream_req` | fn | src/backends.py:106 |
| `_is_failure` | fn | src/backends.py:139 |
| `_phase_nudge` | fn | src/backends.py:147 |
| `_read_covered` | fn | src/backends.py:170 |
| `_read_union` | fn | src/backends.py:177 |
| `_is_redundant_read` | fn | src/backends.py:188 |
| `_track_read` | fn | src/backends.py:200 |
| `_compact_iteration_history` | fn | src/backends.py:215 |
| `_tok` | fn | src/backends.py:228 |
| `_trim_iteration_history` | fn | src/backends.py:307 |
| `_tok` | fn | src/backends.py:321 |
| `OpenAICompatible` | class | src/backends.py:377 |
| `__init__` | fn | src/backends.py:378 |
| `_headers` | fn | src/backends.py:383 |
| `_url` | fn | src/backends.py:389 |
| `_model` | fn | src/backends.py:394 |
| `_check_api_key` | fn | src/backends.py:399 |
| `chat` | fn | src/backends.py:404 |
| `chat_with_tools` | fn | src/backends.py:415 |
| `AnthropicBackend` | class | src/backends.py:583 |
| `__init__` | fn | src/backends.py:584 |
| `_headers` | fn | src/backends.py:589 |
| `_model` | fn | src/backends.py:594 |
| `_split_system` | fn | src/backends.py:597 |
| `chat` | fn | src/backends.py:604 |
| ... | *404 more* | |

### API Endpoints (1)
| Method | Path | File:Line |
|--------|------|-----------|
| ? | `/api/orders` | tests/test_units.py:569 |

### Data Models (1)
| Name | File |
|------|------|
| `Order` | tests/test_units.py |
