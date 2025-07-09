import yaml
import os

def load_config(config_path="config/config.yaml"):
    with open(config_path, encoding='utf-8') as f:
        cfg = yaml.safe_load(f)
    cid = cfg['cliente_id']
    # Popola i parametri derivati se non già specificati
    cfg.setdefault('drive_input_path', f'G:/Drive condivisi/Nexty Docs/{cid}/raw')
    cfg.setdefault('md_output_path', 'output/timmy_kb')
    cfg.setdefault('github_repo', f'nextybase/timmy-kb-{cid}')
    cfg.setdefault('github_branch', 'main')
    cfg.setdefault('gitbook_space', f'Timmy-KB-{cid}')
    return cfg
