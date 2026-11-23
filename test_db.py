from db import get_db_connection

try:
    connection = get_db_connection()

    if connection.is_connected():
        print("SUCCESS: MySQL database connected!")
        print("Database:", connection.database)

    connection.close()

except Exception as e:
    print("DATABASE CONNECTION FAILED")
    print("Error:", e)