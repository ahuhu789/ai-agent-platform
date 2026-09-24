from llm_factory import load_config, LLMFactory, LLMRequest

config = load_config("llm_factory/config.yaml")
llm = LLMFactory.create(config)

while True:
    question = input("You: ")

    if question.lower() in {"exit", "quit"}:
        break

    response = llm.generate(
        LLMRequest(
            messages=[
                {"role": "user", "content": question}
            ]
        )
    )

    print("AI:", response.content)
