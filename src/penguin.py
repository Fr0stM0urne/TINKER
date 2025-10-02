import subprocess, os

def penguin_init(config, fw):
    print(f"\n===== Running Penguin INIT =====", flush=True)
    cmd = [ "penguin", "--image", config['Penguin']['image'], "init", fw ]
    print(f"[cmd] {cmd}", flush=True)
    result = subprocess.run(cmd)

def penguin_run(config, penguin_proj):
    print(f"\n===== Running Penguin for {config['Penguin']['iteration_timeout']} minutes =====", flush=True)
    timeout = int(config['Penguin']['iteration_timeout']) * 60
    firmware_config = penguin_proj / "config.yaml"
    cmd = [ "penguin", "--image", config['Penguin']['image'], "run", firmware_config,
            "--timeout", str(timeout)
    ]
    result = subprocess.run(cmd)