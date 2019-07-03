import discord
import sqlite3
import time
import asyncio
from discord.ext import commands
from discord_token import token as token
#import re

# if discord won't let me slow mode a single user and not the others,
#    I'll simply make a bot to let me achieve the same.
#        Goal is to change the posting privileges in that channel
#        After determined time-frame, restore permission to post by dropping override.

database = sqlite3.connect('messages.db')
sql_c = database.cursor()

bot = commands.Bot(command_prefix='$', description='I am Anti-Spam.')

escalate = {1: 300, 2: 2700, 3: 21600, 4: 151200, 5: 907200, 6: 4536000}  # the mute durations for repeat offences
period = 1  # the duration between un-mute / de-escalate checks
warn_only = True

logging_channel = 'mute-log'

@bot.event
async def on_ready():
    sql_c.execute('create table if not exists messages (' +
                  'channel text, ' +        # 0
                  'id text, ' +             # 1
                  'escalate integer, ' +    # 2
                  'muted integer, ' +       # 3
                  'expire integer, ' +      # 4
                  'messages integer, ' +    # 5
                  'm1 text, ' +             # 6
                  'm2 text, ' +             # 7
                  'm3 text, ' +             # 8
                  'm4 text, ' +             # 9
                  'm5 text,  ' +            # 10
                  'primary key (channel, id));')
    sql_c.execute('create table if not exists ignoring (' +
                  'channel text primary key);')
    sql_c.execute('pragma synchronous = 1')
    sql_c.execute('pragma journal_mode = wal')
    database.commit()
    bot.loop.create_task(process_task())
    log = [x for x in bot.get_all_channels() if x.name == logging_channel][0]
    bot.chatlog = log
    await bot.change_presence(status=discord.Status.idle,
                              activity=discord.Activity(name='you',
                                                        type=4))
    print('ready')


async def update_messages(message, rep):
    channel = message.channel.id
    author = message.author.mention
    saved = read_messages_per_channel(channel, author)
    if saved:
        saved = list(saved[0])
        saved[5] += 1
        saved[10] = saved[9]
        saved[9] = saved[8]
        saved[8] = saved[7]
        saved[7] = saved[6]
        saved[6] = message.content
    else:
        saved = [channel, author, 0, 0, 0, 1, message.content, '', '', '', '']

    recent = False
    if rep < 1:
        rep = message_repetition(' '.join(saved[-5:]))
        recent = rep > 1

    if rep > 1:  # muting
        rep2 = rep * 100
        if warn_only:
            await message.channel.send('Warnings only is ' + ('enabled' if warn_only else 'disabled') +
                                       ' until I am satisfied its working correctly\n' +
                                       'I want to mute ' +
                                       message.author.name +
                                       ' in ' + message.channel.name +
                                       ' for ' + str(escalate[max(1, saved[2])]) + ' seconds'
                                       ' because ' + ('recent messages exceed' if recent else 'that message exceeded') +
                                       ' 100%% with a score of %3.3f%%' % rep2)
        if not warn_only:
            saved[2] = min(6, saved[2] + 1)
            saved[3] = 1  # muted
            saved[4] = int(time.time()) + escalate[saved[2]]
            await mute_user(message, message.author)
        else:
            saved[2] = 1
            saved[4] = int(time.time()) + escalate[saved[2]]
    write_database(saved)


def read_messages_per_channel(channel, uid):
    if not isinstance(channel, int):
        channel = channel.id
    if not isinstance(uid, str):
        uid = uid.mention
    d = sql_c.execute('select * from messages where channel=? and id=?;', (str(channel), uid,)).fetchall()
    return d


def read_messages(uid):
    if not isinstance(uid, str):
        uid = uid.mention
    return sql_c.execute('select * from messages where id=?;', (uid,)).fetchall()


def write_database(row):
    sql_c.execute('insert or replace into messages (channel, id, escalate, muted, expire, messages, m1, m2, m3, m4, ' +
                  'm5) values ("%s", "%s", %d, %d, %d, %d, "%s", "%s", "%s", "%s", "%s")' % (row[0], row[1], row[2],
                                                                                             row[3], row[4], row[5],
                                                                                             row[6], row[7], row[8],
                                                                                             row[9], row[10]))
    database.commit()


def get_expired(time_s):
    return sql_c.execute(f'select * from messages where escalate > 0 and expire <= {time_s}').fetchall()


async def process_expired():
    now = int(time.time())
    expired = get_expired(now)
    if expired:
        for user in expired:
            channel = bot.get_channel(int(user[0]))
            author = bot.get_user(int(user[1][2:-1]))
            relax = now - user[4]
            if user[3] and relax > 0:
                await un_mute_user(channel, author, data=user)
            elif relax > escalate[user[2]]:  # they've been good for a while
                user = list(user)
                user[4] = now  # reset expiry to now to lapse the next escalation
                user[2] -= 1   # deescalate
                write_database(user)
    expired = None


async def process_task():
    while True:
        await asyncio.sleep(period)
        await process_expired()


@bot.event
async def on_message(message):
    if message.author.bot:
        return
    rep = 0
    roles = [role.name for role in message.author.roles]
    ignored = sql_c.execute('select channel from ignoring').fetchall()
    if not ignored:
        ignored = []
    ignored = [x[0] for x in ignored]
    command = (await bot.get_context(message))
    command = command.valid
    if message.channel.name not in ignored and 'Admins' not in roles and not command:
        rep = message_repetition(message.content.upper())
        await update_messages(message, rep)
    if rep <= 1:
        await bot.process_commands(message)


@bot.command(pass_context=True)
@commands.has_role('Admins')
async def mute(ctx, member: discord.Member):
    """mutes the mentioned user on the channel the mute is called from
    will increment their current escalation and set the duration accordingly"""
    await mute_user(ctx.message, member, ctx=ctx)


@bot.command(pass_context=True, hidden=True)
async def get_perms(message, member: discord.Member):
    overwrite = message.channel.overwrites_for(member)
    for k in dir(overwrite):
        if '_' != k[0]:
            print('\t', k, getattr(overwrite, k))


@bot.command(pass_context=True)
@commands.has_role('Admins')
async def unmute(ctx, member: discord.Member):
    """unmutes the mentioned user on the channel the mute is called from
    will reset the message history and start expiring"""
    await un_mute_user(ctx.channel, member, ctx=ctx)


async def mute_user(message, member: discord.member, data=None, ctx=None):
    overwrite = message.channel.overwrites_for(member) or discord.PermissionOverwrite()
    overwrite.send_messages = False
    overwrite.send_tts_messages = False
    overwrite.speak = False
    await message.channel.set_permissions(member, overwrite=overwrite)

    if not data:
        channel = message.channel.id
        author = member.mention
        saved = read_messages_per_channel(channel, author)
        if saved:
            saved = list(saved[0])
            saved[2] = min(6, saved[2] + 1)
            saved[3] = 1
        else:
            saved = [channel, author, 1, 1, 0, 0, '', '', '', '', '']
        saved[4] = int(time.time()) + escalate[saved[2]]
        data = saved
    write_database(data)

    if ctx:
        # noinspection PyUnresolvedReferences
        await bot.chatlog.send(('Muting %s because ' % member.name) + ctx.message.author.name + ' called $mute on them')
    else:
        # noinspection PyUnresolvedReferences
        await bot.chatlog.send('Muting as a consequence of chat exceeding spam score.')


async def un_mute_user(channel: discord.TextChannel, member: discord.Member, data=None, ctx=None):
    # noinspection PyTypeChecker
    await channel.set_permissions(member, overwrite=None)
    if not data:
        channel = channel.id
        author = member.mention
        saved = read_messages_per_channel(channel, author)
        if saved:
            saved = list(saved[0])
            data = saved
    else:
        data = list(data)
    data[2] = max(0, data[2] - 1)
    data[3] = 0
    data[4] = int(time.time())
    data[6] = ''  # clear recent message history, so it doesn't re-mute them as soon as they speak do to recent history
    data[7] = ''
    data[8] = ''
    data[9] = ''
    data[10] = ''
    write_database(data)

    if ctx:
        # noinspection PyUnresolvedReferences
        await bot.chatlog.send(('Un-muting %s because ' % member.name) + ctx.message.author.name + ' called $unmute on them')
    else:
        # noinspection PyUnresolvedReferences
        await bot.chatlog.send('Un-muting %s due to expiration date.' % member.name)


def message_repetition(message):
    mid_point = max(1, int(len(message) / 2 + 0.5))
    per = 1 / mid_point
    repeats = [0]*len(message)
    for i in range(mid_point):
        for j in range(1, len(message)):
            sub_str = message[i:j+i]
            if ' ' not in sub_str or j > 2:
                matches = message.count(sub_str, i) - 1
                repeats[j] += matches * j * per
    return sum(repeats) / mid_point

#
# # noinspection RegExpRedundantEscape
# def drop_domains(message):
#     pattern = re.compile('((http|https)\:\/\/)?[a-zA-Z0-9\.\/\?\:@\-_=#]+\.([a-zA-Z]){2,' +
#                         '6}([a-zA-Z0-9\.\&\/\?\:@\-_=#])*')
#     matches = re.findall(pattern, message)
#     for match in matches:
#         re.sub()


@bot.command(pass_context=True)
@commands.has_role('Admins')
async def ignore(ctx, channel=None):
    """marks a channel as ignored by Anti-Spam
    ignored channels are not monitored at all."""
    if channel is None:
        ctx.send('channel is a required argument')
    sql_c.execute('insert or replace into ignoring (channel) values (?)', (channel,))
    database.commit()


@bot.command(pass_context=True)
@commands.has_role('Admins')
async def watch(ctx, channel=None):
    """marks an ignored channel as being watched"""
    if channel is None:
        ctx.send('channel is a required argument')
    sql_c.execute('delete from ignoring where channel=?', (channel,))
    database.commit()


@bot.command(pass_context=True)
async def expire(ctx, member: discord.Member):
    """gets the current mute state of the user across all channels on the server"""
    author = member.mention
    channels = read_messages(author)
#    channels = [x for x in channels if channels[2] > 0]
    embed = discord.Embed(title=member.name + '\'s escalation state per channel')
    now = int(time.time())
    for mute in channels:
        channel = bot.get_channel(int(mute[0]))
        s = 'Level %d\n' % mute[2]
        if mute[3]:
            s += 'Muted: True\n'
            expire = mute[4] - now
            s += 'Expires %ds' % expire
        else:
            s += 'Muted: False\n'
            if mute[2] > 0:
                expire = escalate[mute[2]] - (now - mute[4])
                print(escalate[mute[2]], (now - mute[4]), now, mute[4])
                s += 'Expires %ds' % expire
        embed.add_field(name=channel.name, value=s)
    await ctx.send(embed=embed)


@bot.command(pass_context=True)
@commands.has_role('Admins')
async def ignored(ctx):
    """outputs a list of the channels currently being ignored by Anti-Spam"""
    ignore = sql_c.execute('select * from ignoring').fetchall()
    ignore = [x[0] for x in ignore]
    if ignore:
        ignore = ', '.join(ignore)
    else:
        ignore = 'None'
    await ctx.send('The following channels are not monitored for anti_spam: ' + ignore)

bot.run(token())

