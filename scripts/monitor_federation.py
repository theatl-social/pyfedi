#!/usr/bin/env python3
"""
Real-time federation monitoring script
Shows Redis Streams status, worker health, and performance metrics
"""
import sys
import time
import redis
import json
from datetime import datetime, timedelta
from collections import defaultdict
import click
from rich.console import Console
from rich.table import Table
from rich.live import Live
from rich.panel import Panel
from rich.layout import Layout
from rich.progress import Progress, SpinnerColumn, TextColumn


console = Console()


class FederationMonitor:
    """Monitor federation activity in real-time"""
    
    def __init__(self, redis_url):
        self.redis_client = redis.from_url(redis_url)
        self.console = Console()
        self.stats = defaultdict(int)
        
    def get_stream_info(self):
        """Get information about all federation streams"""
        streams = {}
        priorities = ['critical', 'high', 'medium', 'low']
        
        for priority in priorities:
            stream_name = f'federation:stream:{priority}'
            try:
                info = self.redis_client.xinfo_stream(stream_name)
                streams[priority] = {
                    'length': info['length'],
                    'groups': info['groups'],
                    'first_entry': info['first-entry'],
                    'last_entry': info['last-entry']
                }
            except redis.ResponseError:
                streams[priority] = {'length': 0, 'groups': 0}
                
        return streams
    
    def get_worker_status(self):
        """Get status of all workers"""
        workers = {}
        worker_keys = self.redis_client.hgetall('federation:workers')
        
        for worker_id, data in worker_keys.items():
            try:
                worker_data = json.loads(data)
                last_heartbeat = datetime.fromisoformat(worker_data['last_heartbeat'])
                age = (datetime.now(timezone.utc) - last_heartbeat).total_seconds()
                
                workers[worker_id.decode()] = {
                    'status': 'healthy' if age < 30 else 'stale',
                    'last_seen': age,
                    'tasks_processed': worker_data.get('tasks_processed', 0),
                    'current_task': worker_data.get('current_task', 'idle')
                }
            except (json.JSONDecodeError, KeyError):
                workers[worker_id.decode()] = {'status': 'error'}
                
        return workers
    
    def get_dlq_stats(self):
        """Get Dead Letter Queue statistics"""
        dlq_name = 'federation:dlq'
        try:
            length = self.redis_client.xlen(dlq_name)
            
            # Get sample of recent failures
            recent = self.redis_client.xrevrange(dlq_name, count=5)
            failures = []
            
            for msg_id, data in recent:
                try:
                    task_data = json.loads(data[b'task'])
                    failures.append({
                        'type': task_data.get('type', 'unknown'),
                        'error': data.get(b'error', b'').decode(),
                        'time': data.get(b'failed_at', b'').decode()
                    })
                except:
                    pass
                    
            return {'count': length, 'recent_failures': failures}
        except redis.ResponseError:
            return {'count': 0, 'recent_failures': []}
    
    def get_processing_rate(self):
        """Calculate processing rate over last minute"""
        now = datetime., timezone()
        minute_ago = now - timedelta(minutes=1)
        
        # Get processed count from monitoring keys
        processed = 0
        pattern = 'federation:stats:processed:*'
        
        for key in self.redis_client.scan_iter(match=pattern):
            timestamp = key.decode().split(':')[-1]
            try:
                ts = datetime.fromisoformat(timestamp)
                if ts >= minute_ago:
                    count = self.redis_client.get(key)
                    if count:
                        processed += int(count)
            except:
                pass
                
        return processed
    
    def create_dashboard(self):
        """Create monitoring dashboard"""
        layout = Layout()
        
        # Get current data
        streams = self.get_stream_info()
        workers = self.get_worker_status()
        dlq = self.get_dlq_stats()
        rate = self.get_processing_rate()
        
        # Streams table
        streams_table = Table(title="Federation Streams")
        streams_table.add_column("Priority", style="cyan")
        streams_table.add_column("Pending", style="yellow")
        streams_table.add_column("Consumer Groups", style="green")
        
        for priority, info in streams.items():
            streams_table.add_row(
                priority.upper(),
                str(info['length']),
                str(info['groups'])
            )
        
        # Workers table
        workers_table = Table(title="Workers")
        workers_table.add_column("Worker ID", style="cyan")
        workers_table.add_column("Status", style="green")
        workers_table.add_column("Last Seen", style="yellow")
        workers_table.add_column("Tasks", style="magenta")
        
        for worker_id, info in workers.items():
            status_style = "green" if info['status'] == 'healthy' else "red"
            workers_table.add_row(
                worker_id,
                f"[{status_style}]{info['status']}[/{status_style}]",
                f"{info.get('last_seen', 0):.1f}s ago",
                str(info.get('tasks_processed', 0))
            )
        
        # Stats panel
        stats_text = f"""
[bold]Performance Metrics[/bold]
Processing Rate: [green]{rate}[/green] tasks/minute
DLQ Count: [red]{dlq['count']}[/red] failed tasks

[bold]System Health[/bold]
Active Workers: {len([w for w in workers.values() if w.get('status') == 'healthy'])}
Total Pending: {sum(s['length'] for s in streams.values())}
        """
        
        # Layout assembly
        layout.split_column(
            Layout(streams_table, name="streams"),
            Layout(workers_table, name="workers"),
            Layout(Panel(stats_text, title="Statistics"), name="stats")
        )
        
        return layout


@click.command()
@click.option('--redis-url', default='redis://localhost:6379/0', help='Redis connection URL')
@click.option('--refresh', default=2, help='Refresh interval in seconds')
def monitor(redis_url, refresh):
    """Monitor federation in real-time"""
    monitor = FederationMonitor(redis_url)
    
    console.print("[bold green]PeachPie Federation Monitor[/bold green]")
    console.print(f"Redis: {redis_url}")
    console.print(f"Refresh: {refresh}s")
    console.print("-" * 50)
    
    try:
        with Live(monitor.create_dashboard(), refresh_per_second=1/refresh) as live:
            while True:
                time.sleep(refresh)
                live.update(monitor.create_dashboard())
                
    except KeyboardInterrupt:
        console.print("\n[yellow]Monitoring stopped[/yellow]")
        

if __name__ == '__main__':
    monitor()