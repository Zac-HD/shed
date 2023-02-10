from test_expected_output import test_saved_examples
import pathlib

if __name__ == "__main__":
    for file in pathlib.Path(__file__).parent.glob("recorded/**/*.txt"):
        print("FILE NAME: ", file)
        test_saved_examples(filename=file, min_version=(3, 7))