#!/usr/bin/env python3
from dotenv import load_dotenv
from langchain.chains import RetrievalQA
from langchain.embeddings import HuggingFaceEmbeddings
from langchain.callbacks.streaming_stdout import StreamingStdOutCallbackHandler
from langchain.vectorstores import Chroma
from langchain.llms import GPT4All, LlamaCpp
import chromadb
import os
import argparse
import time

from fastapi import FastAPI

app = FastAPI()

if not load_dotenv():
    print(
        "Could not load .env file or it is empty. Please check if it exists and is readable."
    )
    exit(1)

embeddings_model_name = os.environ.get("EMBEDDINGS_MODEL_NAME")
persist_directory = os.environ.get("PERSIST_DIRECTORY")

model_type = os.environ.get("MODEL_TYPE")
model_path = os.environ.get("MODEL_PATH")
model_n_ctx = os.environ.get("MODEL_N_CTX")
model_n_batch = int(os.environ.get("MODEL_N_BATCH", 8))
target_source_chunks = int(os.environ.get("TARGET_SOURCE_CHUNKS", 4))

from constants import CHROMA_SETTINGS

# Parse the command line arguments
embeddings = HuggingFaceEmbeddings(model_name=embeddings_model_name)
chroma_client = chromadb.PersistentClient(
    settings=CHROMA_SETTINGS, path=persist_directory
)
db = Chroma(
    persist_directory=persist_directory,
    embedding_function=embeddings,
    client_settings=CHROMA_SETTINGS,
    client=chroma_client,
)
retriever = db.as_retriever(search_kwargs={"k": target_source_chunks})
# activate/deactivate the streaming StdOut callback for LLMs
callbacks = []  # if args.mute_stream else [StreamingStdOutCallbackHandler()]
# Prepare the LLM
match model_type:
    case "LlamaCpp":
        llm = LlamaCpp(
            model_path=model_path,
            max_tokens=model_n_ctx,
            n_batch=model_n_batch,
            callbacks=callbacks,
            verbose=False,
        )
    case "GPT4All":
        llm = GPT4All(
            model=model_path,
            max_tokens=model_n_ctx,
            backend="gptj",
            n_batch=model_n_batch,
            callbacks=callbacks,
            verbose=False,
        )
    case _default:
        # raise exception if model_type is not supported
        raise Exception(
            f"Model type {model_type} is not supported. Please choose one of the following: LlamaCpp, GPT4All"
        )

qa = RetrievalQA.from_chain_type(
    llm=llm,
    chain_type="stuff",
    retriever=retriever,
    return_source_documents=True,
)
# Interactive questions and answers


# post request with question
@app.post("/question")
async def question(question: str):
    # Get the answer from the chain
    start_time = time.time()
    res = qa(question)
    end_time = time.time()
    answer, docs = (
        res["result"],
        [] if "source_documents" not in res else res["source_documents"],
    )

    return {
        "answer": answer,
        "documents": {
            {"source": document.metadata["source"], "content": document.page_content}
            for document in docs
        },
        "time_taken": end_time - start_time,
    }
