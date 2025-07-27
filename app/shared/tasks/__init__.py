from flask import current_app


def task_selector(task_key, send_async=True, **kwargs):
    # Import tasks here to avoid circular imports
    from app.shared.tasks.follows import join_community, leave_community
    from app.shared.tasks.likes import vote_for_post, vote_for_reply
    from app.shared.tasks.notes import make_reply, edit_reply
    from app.shared.tasks.deletes import delete_reply, restore_reply, delete_post, restore_post, delete_community, \
        restore_community, delete_posts_with_blocked_images
    from app.shared.tasks.flags import report_reply, report_post
    from app.shared.tasks.pages import make_post, edit_post
    from app.shared.tasks.locks import lock_post, unlock_post
    from app.shared.tasks.adds import sticky_post, add_mod
    from app.shared.tasks.removes import unsticky_post, remove_mod
    from app.shared.tasks.groups import edit_community
    from app.shared.tasks.users import check_user_application
    from app.shared.tasks.blocks import ban_from_community, unban_from_community, ban_from_site, unban_from_site
    
    # Debug: Print the actual task name
    current_app.logger.info(f'task_selector: vote_for_post task name is {vote_for_post.name}')
    
    tasks = {
        'join_community': join_community,
        'leave_community': leave_community,
        'vote_for_post': vote_for_post,
        'vote_for_reply': vote_for_reply,
        'make_reply': make_reply,
        'edit_reply': edit_reply,
        'delete_reply': delete_reply,
        'restore_reply': restore_reply,
        'report_reply': report_reply,
        'make_post': make_post,
        'edit_post': edit_post,
        'delete_post': delete_post,
        'restore_post': restore_post,
        'report_post': report_post,
        'lock_post': lock_post,
        'unlock_post': unlock_post,
        'sticky_post': sticky_post,
        'unsticky_post': unsticky_post,
        'edit_community': edit_community,
        'delete_community': delete_community,
        'restore_community': restore_community,
        'delete_posts_with_blocked_images': delete_posts_with_blocked_images,
        'check_application': check_user_application,
        'ban_from_community': ban_from_community,
        'unban_from_community': unban_from_community,
        'ban_from_site': ban_from_site,
        'unban_from_site': unban_from_site,
        'add_mod': add_mod,
        'remove_mod': remove_mod,
    }

    if current_app.debug:
        send_async = False
        current_app.logger.info(f'task_selector: debug mode, forcing sync execution for {task_key}')

    if send_async:
        current_app.logger.info(f'task_selector: dispatching {task_key} async with kwargs: {kwargs}')
        # Debug: Check Celery configuration
        from app import celery
        current_app.logger.info(f'task_selector: Celery broker URL is {celery.conf.broker_url}')
        
        # Log which queue this task will go to
        task_routes = celery.conf.get('CELERY_ROUTES', {})
        task_name = tasks[task_key].name
        if task_name in task_routes:
            queue_name = task_routes[task_name].get('queue', 'celery')
        else:
            queue_name = celery.conf.get('CELERY_TASK_DEFAULT_QUEUE', 'celery')
        current_app.logger.info(f'task_selector: Task {task_key} ({task_name}) will be sent to queue: {queue_name}')
        
        result = tasks[task_key].delay(**kwargs)
        current_app.logger.info(f'task_selector: Celery task {task_key} dispatched with id={result.id}')
    else:
        current_app.logger.info(f'task_selector: executing {task_key} synchronously with kwargs: {kwargs}')
        return tasks[task_key](**kwargs)

