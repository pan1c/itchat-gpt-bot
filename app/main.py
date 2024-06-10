from modules.telegram_messages_handler import main

# Entry point of the application
if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
