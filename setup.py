#!/usr/bin/env python3
"""
Setup script for Chevy Q&A Agent.
This script helps set up the environment and configuration for the Chevy Q&A Agent.
"""

import argparse
import os
import sys
from pathlib import Path


def create_env_file():
    """Create a .env file prompting for OpenAI credentials.

    Prompts for:
    - OPENAI_API_KEY (required)
    - OPENAI_PROJECT (optional but recommended for admin/org keys)
    """
    env_path = Path(".env")
    env_example_path = Path(".env.example")

    # Check if .env already exists
    if env_path.exists():
        print(f"\n[!] A .env file already exists at {env_path.absolute()}")
        overwrite = input("Do you want to overwrite it? (y/n): ").lower().strip() == "y"
        if not overwrite:
            print("Keeping existing .env file.")
            return

    # Get API key from user
    api_key = ""
    while not api_key:
        api_key = input("\nEnter your OpenAI API key: ").strip()
        if not api_key:
            print("[!] API key cannot be empty.")

    # Get optional project id/slug (recommended with admin/org keys)
    project_id = input(
        "Enter your OpenAI Project ID/slug (optional but recommended): "
    ).strip()

    # If .env.example exists, use it as a template
    if env_example_path.exists():
        with open(env_example_path, "r") as f:
            env_content = f.read()
        env_content = env_content.replace("your_openai_api_key_here", api_key)
        if "OPENAI_PROJECT=" in env_content:
            # try to replace placeholder if present
            env_content = env_content.replace("OPENAI_PROJECT=", f"OPENAI_PROJECT={project_id}")
        else:
            env_content += f"\nOPENAI_PROJECT={project_id}\n"
    else:
        # Create basic .env content
        env_content = f"""# Chevy Q&A Agent Environment Configuration
OPENAI_API_KEY={api_key}
# If using an admin/org key, set your project for routing
OPENAI_PROJECT={project_id}
EMBED_MODEL=text-embedding-3-small
CHAT_MODEL=gpt-4o-mini
# Default graph path: prefer new output_embedding location
GRAPH_PATH=output_embedding/embedding.json
"""

    # Write the .env file
    with open(env_path, "w") as f:
        f.write(env_content)

    print(f"[✓] Created .env file at {env_path.absolute()}")


def check_embedding_graph():
    """Check if embedding.json exists, if not offer to generate it"""
    embedding_path = Path("embedding.json")
    output_dev_path = Path("output_DEV.json")
    output_prod_path = Path("output_PROD.json")

    if embedding_path.exists():
        print(f"[✓] Embedding graph found at {embedding_path.absolute()}")
        return True

    print(f"\n[!] Embedding graph not found at {embedding_path.absolute()}")

    # Check if we have any output files to generate from
    if output_dev_path.exists():
        source_path = output_dev_path
    elif output_prod_path.exists():
        source_path = output_prod_path
    else:
        print("[!] No output file found (output_DEV.json or output_PROD.json)")
        print("    You need to run the scraper first to generate an output file.")
        return False

    # Ask if user wants to generate embedding graph
    generate = (
        input(f"Do you want to generate the embedding graph from {source_path}? (y/n): ")
        .lower()
        .strip()
        == "y"
    )
    if generate:
        try:
            print(f"[*] Generating embedding graph from {source_path}...")
            cmd = f"python -m embedding.chevy_embed --input {source_path}"
            os.system(cmd)
            if embedding_path.exists():
                print(f"[✓] Successfully generated embedding graph at {embedding_path.absolute()}")
                return True
            else:
                print(f"[!] Failed to generate embedding graph. Check for errors above.")
                return False
        except Exception as e:
            print(f"[!] Error generating embedding graph: {e}")
            return False
    return False


def main():
    """Main setup function"""
    parser = argparse.ArgumentParser(description="Setup for Chevy Q&A Agent")
    parser.add_argument("--skip-env", action="store_true", help="Skip .env file creation")
    parser.add_argument("--skip-embedding", action="store_true", help="Skip embedding graph check")
    parser.add_argument("--run-agent", action="store_true", help="Run the agent after setup")
    args = parser.parse_args()

    print("\n===== Chevy Q&A Agent Setup =====\n")

    # Create .env file
    if not args.skip_env:
        create_env_file()

    # Check embedding graph
    if not args.skip_embedding:
        check_embedding_graph()

    # Final instructions
    print("\n===== Setup Complete =====")
    print("\nTo run the Q&A Agent, use:")
    print("    python agent.py")

    # Run the agent if requested
    if args.run_agent:
        print("\n[*] Starting Q&A Agent...\n")
        os.system("python agent.py")


if __name__ == "__main__":
    main()
