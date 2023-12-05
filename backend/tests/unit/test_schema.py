from src.schema import schema_inp_to_out


class TestSchema:
    def test_schema_inp_to_out_with_spec(self, spec_feedback_input_output_schema_tuple):
        input_schema, expected_output_schema = spec_feedback_input_output_schema_tuple
        output_schema = schema_inp_to_out(input_schema)
        assert output_schema == expected_output_schema

    def test_schema_inp_to_out_with_container(
        self, container_feedback_input_output_schema_tuple
    ):
        (
            input_schema,
            expected_output_schema,
        ) = container_feedback_input_output_schema_tuple
        output_schema = schema_inp_to_out(input_schema, is_with_spec=False)
        assert output_schema == expected_output_schema
