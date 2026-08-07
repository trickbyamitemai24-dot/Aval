import re

with open("bot.py", "r") as f:
    code = f.read()

replacement = """if __name__ == "__main__":
    # Raise OS file descriptor limit to prevent "too many open files" under massive concurrent load
    try:
        import resource
        soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
        target = min(65536, hard)
        if soft < target:
            resource.setrlimit(resource.RLIMIT_NOFILE, (target, hard))
            logging.getLogger(__name__).info(f"📂 Raised OS file descriptor limit: {soft} -> {target}")
    except Exception as e:
        pass

    main()"""

code = code.replace('if __name__ == "__main__":\n    main()', replacement)

with open("bot.py", "w") as f:
    f.write(code)

print("RLIMIT applied")
