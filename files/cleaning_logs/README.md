# Log sanitization and cleanup scripts

To comply with privacy requirements of the AI Assessment, we have to:
- redact personal information/identifiers from data already stored by the website (embedded logs within json files)
- create a mechanism on the website backend that performs the sanitization automatically upon log upload

# How to use

Do `python3 logs_cleanup.py -h` for help.
The command used to clean the json files on the pod was (from within this directory - `files/cleaning_logs`):
`python3 logs_cleanup.py --output_dir debug/ path_to_json_files/`
It is advisable to check files stored in `debug/` to see if everything went smoothly.
- The logger will output into `output.log`, no errors and ideally no warnings should be present (see Notes).
- `snippets_added.json` will contain text snippets that were added, in case indexes and the source log is present, but no text field.
- By default `OUTPUT_DIR/sanitization_output.txt` will contain information about which data was redacted (unless `--no_auditing` is used).

All files in the `--output_dir` should be then removed/discarded. They are just for checking if the data cleaning and redactions were successful.

# Notes

Some of the older json files have inconsistent snippets (stripped off of some whitespaces) and there might be a bunch of WARNINGs in the log saying that the snippets don't match (there is about ~35 such broken snippets, see the stats on the bottom of the log output).
