import { useMarkAllNotificationsRead, useMarkNotificationRead, useNotificationUnreadCount, useNotifications } from '@/lib/queries';

export default function NotificationsPage() {
  const notificationsQ = useNotifications(false);
  const countQ = useNotificationUnreadCount();
  const markRead = useMarkNotificationRead();
  const markAll = useMarkAllNotificationsRead();
  return (
    <main className="h-full overflow-auto bg-background p-4 text-foreground" data-testid="notifications-page">
      <section className="rounded-xl border border-border/80 bg-card/90 p-4">
        <p className="text-xs uppercase tracking-[0.24em] text-muted-foreground">Notifications</p>
        <h1 className="mt-1 text-2xl font-semibold">Notifications</h1>
        <p className="mt-2 text-sm text-muted-foreground">Unread: { countQ.data?.unreadCount ?? 0 }</p>
        <button className="mt-3 rounded-md border border-border px-3 py-1.5 text-sm" onClick={ () => void markAll.mutateAsync() } type="button">Mark all read</button>
      </section>
      <section className="mt-4 grid gap-2 rounded-xl border border-border/80 bg-card/90 p-4">
        { notificationsQ.data?.map((item) => (
          <article key={ item.id } className="rounded-md border border-border p-3">
            <p className="font-medium">{ item.title }</p>
            <p className="text-sm text-muted-foreground">{ item.body ?? item.type }</p>
            { !item.readAt && <button className="mt-2 rounded-md border border-border px-3 py-1.5 text-sm" onClick={ () => void markRead.mutateAsync(item.id) } type="button">Mark read</button> }
          </article>
        )) }
        { !notificationsQ.data?.length && <p className="text-sm text-muted-foreground">No notifications yet.</p> }
      </section>
    </main>
  );
}
