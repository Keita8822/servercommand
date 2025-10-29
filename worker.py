from rq import Worker, Queue, Connection 
from redis import Redis 
from app.settings import settings 

def main(): 
    redis_conn = Redis.from_url(settings.redis_url) 
    listen = [settings.rq_queue_name] 
    with Connection(redis_conn):
         worker = Worker(list(map(Queue, listen))) 
         worker.work()
         
        
if __name__ == "__main__": 
    main()