"""Preflight checks for source/output aliases, including existing hard links."""
from pathlib import Path


def paths_alias(left, right):
    left, right = Path(left), Path(right)
    return left.resolve() == right.resolve() or (left.exists() and right.exists() and left.samefile(right))


def guard_output_paths(inputs, outputs, *, flat_directories=()):
    """Reject input overwrites and conflicting file/flat-directory outputs.

    Call before creating outputs. This detects existing aliases, not adversarial
    concurrent filesystem changes after the check.
    """
    inputs = [Path(path) for path in inputs if path is not None]
    outputs = [Path(path) for path in outputs]
    for index, output in enumerate(outputs):
        if output.exists() and output.is_dir():
            raise ValueError('A file output path points to an existing directory.')
        if any(paths_alias(output, source) for source in inputs):
            raise ValueError('Output paths must not overwrite input files, including symlink/hard-link aliases.')
        if any(paths_alias(output, previous) for previous in outputs[:index]):
            raise ValueError('Output files must have distinct paths and must not alias each other.')
    directories = list(map(Path, flat_directories))
    for index, directory in enumerate(directories):
        if directory.exists() and not directory.is_dir():
            raise ValueError('An artifact-directory path points to an existing file.')
        if any(paths_alias(directory, previous) for previous in directories[:index]):
            raise ValueError('Artifact directories must have distinct paths.')
        resolved = directory.resolve()
        if any(path.resolve() == resolved or resolved in path.resolve().parents for path in inputs + outputs):
            raise ValueError('Artifact directories must not contain input files or other pipeline outputs.')
        if directory.exists():
            for child in directory.iterdir():
                if any(paths_alias(child, path) for path in inputs + outputs):
                    raise ValueError('An artifact-directory entry aliases an input file or another output.')
