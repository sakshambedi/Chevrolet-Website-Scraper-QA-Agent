import click


@click.command()
@click.option("--input", "-i", required=True, help="Input file path")
@click.option("--output", "-o", required=True, help="Output file path")
def main(input, output):
    # Your main logic here
    print(f"Input file: {input}")
    print(f"Output file: {output}")


if __name__ == "__main__":
    main()
