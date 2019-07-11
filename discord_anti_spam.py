import discord
import sqlite3
import datetime
import asyncio
from discord.ext import commands
from discord.ext.commands import has_permissions
from discord_token import token as token
import re
import os

# todo: warn once per server and then mute
# todo: finish the warning only method
# todo: mute warning expiration - so you can get re-warned if your good for a while. - several hours at least
# todo: publicly posted mod-bot auto response details, so users can know why it will do what it does.
#          include the full list of epithets that earn a 12hr server wide muting.
# todo: finish the garbage detection code and import it here, and produce response code
# todo: implement a racial epithet detection method - automatic 12hr ban if caught.
# todo: implement a profanity detection method - couple with ordinary user complaints to mute offensive outbursts
# todo: implement on_ban, on_kick, on_unban events to also respond to such action when done via discord apps as well.
#

database = sqlite3.connect('messages.db')
sql_c = database.cursor()

bot = commands.Bot(command_prefix='$', description='I am Mod-Bot.')

escalate = {1: 300, 2: 2700, 3: 21600, 4: 151200, 5: 907200, 6: 4536000}  # the mute durations for repeat offences
deescalate_period = 60  # the duration between un-mute / de-escalate checks

message_logs_path = 'message logs/'
today = datetime.datetime.today().day
if not os.path.exists(message_logs_path):
    os.mkdir(message_logs_path)

logging_channel = 'mute-log'
warn_only = True
mutelogs = dict()


message_logs = dict()


class action:
    class unmute:
        name = 'Unmute'
        color = 0x0000ff
    class mute:
        name = 'Mute'
        color = 0xffff00
    class kick:
        name = 'Kick'
        color = 0xff4500
    class unban:
        name = 'Unban'
        color = 0x0000ff
    class ban:
        name = 'Ban'
        color = 0x8b0000


def open_logfile(guild: str, filename: str, mode='a'):
    if not isinstance(guild, str):
        guild = str(guild)
    if not os.path.exists(message_logs_path + guild + '\\' + filename):
        f = open(message_logs_path + guild + '\\' + filename, mode)
        f.write('# logging format is one of either:\n')
        f.write('#   date1:date2 - guild(guild.id):channel(channel.id):user(user.id):message\n')
        f.write('#   date1:date2 - dm:user(user.id):message\n')
        f.write('# DM\'s use the second, normal guild/channel messages use the first\n')
        f.write('# date1 is 2 digits each for year, month, day, hours(24hr), minutes, seconds: yymmddhhMMss\n')
        f.write('# date2 is seconds since epoch ( time.time() ) and is the reference saved with the message in the '
                'database.\n')
        f.write('# messages are saved to the database under the key (channel, uid), and are saved under m# as '
                'time2:message.content, where # is 1-5, representing one of the 5 active history messages\n\n')
        f.flush()
        return f
    else:
        return open(message_logs_path + guild + '\\' + filename, mode)


@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.errors.MissingPermissions):
        await ctx.send(ctx.author.mention + ', ' + str(error))
    else:
        raise error


@bot.event
async def on_ready():
    for guild in bot.guilds:
        if not os.path.exists(message_logs_path + str(guild.id)):
            os.mkdir(message_logs_path + str(guild.id))
        message_logs[guild.id] = open_logfile(guild.id, datetime.datetime.utcnow().strftime('%y%m%d') + '.txt')


#    message_log = open_logfile(time.strftime('%y%m%d') + '.txt')
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
                  'guild integer, ' +
                  'channel integer, ' +
                  'primary key (guild, channel));')
    sql_c.execute('pragma synchronous = 1')
    sql_c.execute('pragma journal_mode = wal')
    database.commit()
    bot.loop.create_task(process_task())
    logs = [x for x in bot.get_all_channels() if x.name == logging_channel]
    for c in logs:
        mutelogs[c.guild] = c

    await bot.change_presence(status=discord.Status.idle, activity=discord.Activity(type=4))
    print('ready')


async def update_messages(message, rep, old_message=None):
    channel = message.channel.id
    author = message.author.mention
    saved = read_messages_per_channel(channel, author)
    if old_message:
        if saved:
            saved = list(saved[0])
            for n in [6, 7, 8, 9, 10]:
                print(saved[n], old_message.content)
                if old_message.content == saved[n].split(':', 1)[1]:
                    print('found it, updating', n)
                    saved[n] = str(int(datetime.datetime.utcnow().timestamp())) + ':' + message.content
                    break
            print(saved)
    else:
        if saved:
            saved = list(saved[0])
            saved[5] += 1
            saved[10] = saved[9]
            saved[9] = saved[8]
            saved[8] = saved[7]
            saved[7] = saved[6]
            saved[6] = str(int(datetime.datetime.utcnow().timestamp())) + ':' + message.content
        else:
            saved = [channel, author, 0, 0, 0, 1,
                     str(int(datetime.datetime.utcnow().timestamp())) + ':' + message.content,
                     '', '', '', '']

    recent = False
    if rep < 1:
        recent_messages = []
        for msg in saved[-5:]:
            msg = msg.split(':', 1)
            if len(msg) > 1:
                recent_messages.append(re.sub('(\^*){1,5}','', msg[1]))
        rep = message_repetition(' '.join(recent_messages))
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
            saved[4] = int(datetime.datetime.utcnow().timestamp()) + escalate[saved[2]]
            await mute_user(message, message.author)
        else:
            saved[2] = 1
            saved[4] = int(datetime.datetime.utcnow().timestamp()) + escalate[saved[2]]
    write_database(saved)
    return rep


async def warning(message, reason):
    await message.send(f'{message.author.mention} I did not like that last message because {reason}, this is your '
                       f'warning.  Behave or I will silence you.')
    sql_c.execute('update expire=? in messages where id=? and expire=0;', (int(datetime.datetime.utcnow().timestamp()),
                                                                           message.author.mention,))


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


async def process_expired():
    now = int(datetime.datetime.utcnow().timestamp())
    query = f"select * from messages where escalate > 0 and expire <= {now} or m1 != ''"
    expired = sql_c.execute(query).fetchall()
    if expired:
        for user in expired:
            channel = bot.get_channel(int(user[0]))
            try:
                author = bot.get_user(int(user[1][2:-1]))
            except ValueError:
                author = bot.get_user(int(user[1][3:-1]))  # some users have an ! in their username
            relax = now - user[4]
            if user[3] and relax > 0:
                await un_mute_user(channel, author, data=user)
            else:
                user = list(user)
                if relax > 0 and user[2] == 0:  # the bot no longer cares, start pruning their history
                    for msg in range(10, 5, -1):
                        if user[msg]:
                            age = int(user[msg].split(':', 1)[0])
                            if now - age >= 60:
                                user[msg] = ''
                                break
                elif relax > escalate[user[2]]:  # they've been good for a while
                    user[4] = now  # reset expiry to now to lapse the next escalation
                    user[2] -= 1   # deescalate
                write_database(user)
    expired = None


async def process_task():
    global message_log
    global today
    while True:
        await asyncio.sleep(deescalate_period)
        await process_expired()
        if datetime.datetime.today().day != today:
            today = datetime.datetime.today().day
            # new log file time
            for guild in message_logs:
                message_logs[guild].close()
                message_logs[guild] = open_logfile(guild, datetime.datetime.utcnow().strftime('%y%m%d') + '.txt')


def log_message(message, dm, old=None):
    t = datetime.datetime.utcnow().strftime(f'%y%m%d%H%M%S:{int(datetime.datetime.utcnow().timestamp())} - ')
    s2 = '' if old is None else '====EDIT====\n\t====OLD====\n\t\t'
    if dm:
        if old:
            s2 += f'dm:{old.author}({old.author.id}):{old.content}\n\t====NEW====\n\t\t'
        s = f'dm:{message.author}({message.author.id}):{message.content}'
    else:
        if old:
            s2 += f'{old.guild.name}({old.guild.id}):{old.channel.name}({old.channel.id}):' + \
                  f'{old.author}({old.author.id}):{old.content}\n\t====NEW====\n\t\t'
        s = f'{message.guild.name}({message.guild.id}):{message.channel.name}({message.channel.id}):' + \
            f'{message.author}({message.author.id}):{message.content}'
        message_logs[message.guild.id].write(t + s2 + s + '\n')
        message_logs[message.guild.id].flush()
    print(t + s)


@bot.event
async def on_message(message):
    if message.author.bot:
        return
    rep = await eval_message(message)
    if rep <= 1:
        await bot.process_commands(message)


@bot.event
async def on_message_edit(old_message, message):
    if message.author.bot:
        return
    await eval_message(message, original=old_message)


async def eval_message(message, original=None):
    t = tard(message.content)
    print(t)
    if t:
        await message.channel.send('^^ '+t)
    dm = not hasattr(message.author, 'guild')
    log_message(message, dm, old=original)
    if dm:
        ignored = []
        admin = False
        command = False
        owner = False
    else:
        admin = any((role.permissions.administrator for role in message.author.roles))
        ignored = sql_c.execute('select * from ignoring where guild=?', (message.guild.id,)).fetchall()
        if ignored:
            ignored = [int(x[1]) for x in ignored]
        else:
            ignored = []
        command = (await bot.get_context(message)).valid
        owner = message.guild.owner.id == message.author.id
    rep = 0

    if not dm and message.channel.id not in ignored and not admin and not command and not owner:
        content = re.sub('(\^*){1,5}', '', message.content.upper())
        rep = message_repetition(content)
        rep = await update_messages(message, rep, old_message=original)
    return rep


def tard(message):
    match = re.match('reee+', message, re.IGNORECASE)
    if not match:
        return None
    match = match.group()
    s = 'T' if match[0] == 'R' else 't'
    for c in match[1:-2]:
        s += 'A' if c == c.upper() else 'a'
    s += 'R' if match[-2] == match[-2].upper() else 'r'
    s += 'D' if match[-1] == match[-1].upper() else 'd'
    return s


@bot.command(pass_context=True)
@has_permissions(ban_members=True, kick_members=True)
async def getlogs(ctx, days: int = None):
    if not days:
        days = 0
    now = datetime.datetime.utcnow()
    while days < 1:
        delta = datetime.timedelta(days=days)
        then = now - delta
        path = message_logs_path + str(ctx.guild.id) + '\\' + then.strftime('%y%m%d') + '.txt'
        if not os.path.exists(path):
            await ctx.author.send('I have no logs for ' + path)
        else:
            await ctx.author.send('your file', file=discord.File(path))
        days += 1


@bot.command(pass_context=True)
@has_permissions(manage_roles=True)
async def mute(ctx, member: discord.Member, *reason):
    """mutes the mentioned user on the channel the mute is called from
    will increment their current escalation and set the duration accordingly
    args is used to collect a 'reason' for the muting"""
    await mute_user(ctx.message, member, *reason, ctx=ctx)


@bot.command(pass_context=True, hidden=True)
async def get_perms(message, member: discord.Member):
    overwrite = message.channel.overwrites_for(member)
    for k in dir(overwrite):
        if '_' != k[0]:
            print('\t', k, getattr(overwrite, k))


@bot.command(pass_context=True)
@has_permissions(manage_roles=True)
async def unmute(ctx, member: discord.Member, *reason):
    """unmutes the mentioned user on the channel the mute is called from
    will reset the message history and start expiring
    args is used to collect a 'reason' for the unmuting"""
    await un_mute_user(ctx.channel, member, *reason, ctx=ctx)


async def mute_user(message, member: discord.member, *reason, data=None, ctx=None):
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
        saved[4] = int(datetime.datetime.utcnow().timestamp()) + escalate[saved[2]]
        data = saved
    write_database(data)
    await log_action(ctx, action.mute, member.mention, reason)
    # mutelog = mutelogs.get(ctx.guild, None)
    # if mutelog:
    #     if ctx:
    #         if not reason:
    #             reason = ('No', 'Reason')
    #         await log_action(mutelog, action.mute, ctx.message.author.mention, member, ' '.join(reason))
    #     else:
    #         await log_action(mutelog, action.mute, bot.user.name, member, 'Spam threshold exceeded')


async def un_mute_user(channel: discord.TextChannel, member: discord.Member, *reason, data=None, ctx=None):
    # noinspection PyTypeChecker
    await channel.set_permissions(member, overwrite=None)
    if not data:
        saved = read_messages_per_channel(channel.id, member.mention)
        if saved:
            saved = list(saved[0])
            data = saved
    else:
        data = list(data)
    data[2] = max(0, data[2] - 1)
    data[3] = 0
    data[4] = int(datetime.datetime.utcnow().timestamp())
    data[6] = ''  # clear recent message history, so it doesn't re-mute them as soon as they speak do to recent history
    data[7] = ''
    data[8] = ''
    data[9] = ''
    data[10] = ''
    write_database(data)
    await log_action(ctx, action.unmute, member.mention, reason)
    #
    # mutelog = mutelogs.get(ctx.guild, None)
    # if mutelog:
    #     if ctx:
    #         if not reason:
    #             reason = ('No', 'Reason')
    #         await log_action(mutelog, action.unmute, ctx.message.author.mention, member.mention, ' '.join(reason))
    #     else:
    #         await log_action(mutelog, action.unmute, bot.user.name, member.mention, 'Time served')


async def log_action(ctx, act, who, why):
    mutelog = mutelogs.get(ctx.guild, None)

    if mutelog:
        if ctx:
            if not why:
                why = ('No', 'Reason')
            issuer = ctx.message.author.mention
            why = ' '.join(why)
        else:
            issuer = bot.user.name
            why = 'Spam threshold exceeded' if isinstance(act, action.mute) else 'Time served'

        embed = discord.Embed()
        embed.add_field(name='Issuer: ', value=issuer)
        embed.add_field(name='Action: ', value=act.name)
        embed.add_field(name='Who:    ', value=who)
        embed.add_field(name='Why:    ', value=why)
        embed.colour = act.color
        await mutelog.send(embed=embed)


@bot.command(pass_context=True)
@has_permissions(manage_messages=True)
async def showmessages(ctx, member: discord.Member = None):
    """prints the given user's recent messages, oldest first, split across several messages if necessary"""
    if not member:
        return await ctx.send('A member name is required to see their recent messages')
    query = 'select m5, m4, m3, m2, m1 from messages where channel=? and id=?;'
    recent = sql_c.execute(query, (ctx.channel.id, member.mention,)).fetchall()
    if recent:
        recent = recent[0]  # drop the outer array layer
    title = f'{member.display_name}\'s recent messages'
    embed = discord.Embed()
    embed1 = None
    embed2 = None
    embed3 = None
    length = 0
    for i, message in enumerate([m.split(':', 1) for m in recent]):
        if len(message) == 2 and isinstance(message, list):
            message = message[1]
        if message != '':
            if len(message) + length > 5500:
                if embed1 and embed2:
                    embed3 = embed
                elif embed1:
                    embed2 = embed
                else:
                    embed1 = embed
                embed = discord.Embed()
                length = 0

            if len(message) > 1012:
                embed.add_field(name=str(i - len(recent)) + '.1', inline=False, value=message[:1012])
                embed.add_field(name=str(i - len(recent)) + '.2', inline=False, value=message[1012:])
            else:
                embed.add_field(name=str(i-len(recent)), inline=False, value=message)
            length += len(message)

    if embed1 and embed2:
        embed3 = embed
    elif embed1:
        embed2 = embed
    else:
        embed1 = embed

    if embed3:
        embed1.title = title + ', part 1'
        embed2.title = title + ', part 2'
        embed3.title = title + ', part 3'
    elif embed2:
        embed1.title = title + ', part 1'
        embed2.title = title + ', part 2'
    else:
        embed1.title = title

    await ctx.send(embed=embed1)
    if embed2:
        await ctx.send(embed=embed2)
    if embed3:
        await ctx.send(embed=embed3)


@bot.command(pass_context=True)
@has_permissions(ban_members=True)
async def ban(ctx, member: discord.Member, *reason, delete=0):
    """bans a user via mention from the current guild
    delete_messages is how many days of previous messages to remove
    eg, ban @Traven shoes obsession delete=7
         bans Traven with the reason 'shoes obsession', and removes the last 7 days of his messages
    """
#    reason = ' '.join(reason)
    await log_action(ctx, action.ban, member.mention, reason)
    reason = ' '.join(reason)
    await ctx.guild.ban(member, reason=reason, delete_message_days=delete)


@bot.command(pass_context=True)
@has_permissions(ban_members=True)
async def banid(ctx, uid: int, *reason, delete=0):
    """bans a user via uid# from the current guild
    delete_messages is how many days of previous messages to remove
    eg, ban 598399316654292993 racism delete=7
         bans the user with that id with the reason 'racism', and removes the last 7 days of his messages
    """

    # ban them via discord.Object(id=uid)
    # then lookup their user object via ctx.guild.bans() since I can get it that way.
    user = discord.Object(id=uid)
    await ctx.guild.ban(user, reason=' '.join(reason), delete_message_days=delete)
    bans = await ctx.guild.bans()
    for b in bans:
        if b.user.id == uid:
            user = b.user
    if hasattr(user, 'mention'):
        await log_action(ctx, action.ban, f'{user.mention}', reason)
    elif hasattr(user, 'name') and hasattr(user, 'discriminator'):
        await log_action(ctx, action.ban, f'{user.name}#{user.discriminator}', reason)
    else:
        await log_action(ctx, action.ban, f'@<{uid}>', reason)


@bot.command(pass_context=True, hidden=True)
async def user(ctx, uid: int):
    await get_user(ctx, uid)


async def get_user(ctx, uid: int):
    if isinstance(uid, str) and '@' in uid:
        try:
            uid = int(uid[2:-1])
        except ValueError:
            try:
                uid = int(uid[3:-1])
            except ValueError:
                return await ctx.send(f'I can\'t find {uid} as a member of this server to reference via mention, '
                                      f'use their id instead')
    else:
        uid = int(uid)
    user = bot.get_user(uid)
    print(user)
    return user


@bot.command(pass_context=True)
@has_permissions(ban_members=True)
async def unban(ctx, uid, *reason):
    # async def unban(ctx, member, *reason):

    """un-bans a user from the current guild
    eg, unban uid because I want to?
         unbans the user for which  user.id == uid with the reason 'because I want to?'
    """
    if '@' in uid:
         try:
             uid = int(uid[2:-1])
         except ValueError:
             try:
                 uid = int(uid[3:-1])
             except ValueError:
                 return await ctx.send(f'I can\'t find {uid} as a member of this server to reference via mention, '
                                f'use their id instead')
    else:
        uid = int(uid)
    bans = await ctx.guild.bans()
    if bans:
        for u in bans:
            if u.user.id == uid:
                target = u.user
                await log_action(ctx, action.unban, target.mention, reason)
                reason = ' '.join(reason)
                await ctx.guild.unban(target, reason=reason)
                # mutelog = mutelogs.get(ctx.guild, None)
                # if mutelog:
                #     if not reason:
                #         reason = ('No', 'Reason')
                #     await log_action(mutelog, action.unban, ctx.message.author.mention, target.mention, reason)
                break


@bot.command(pass_context=True)
@has_permissions(ban_members=True)
async def banned(ctx):
    """shows the banned users and the reason given"""
    bans = await ctx.guild.bans()
    if not bans:
        return await ctx.send('There are no banned users at this time')
    embed = None
    for i, userban in enumerate(bans):
        if i % 25 == 0:
            if embed:
                await ctx.send(embed=embed)
            embed = discord.Embed(title='Banned users')
        embed.add_field(name=str(userban.user)+'\n' + str(userban.user.id), value=userban.reason, inline=False)
    await ctx.send(embed=embed)


@bot.command(pass_context=True)
@has_permissions(ban_members=True)
async def banneduser(ctx, member: discord.Member):
    """gets a banned user and shows the reason why"""
    userban = await ctx.guild.fetch_ban(member)
    await ctx.send(f'{userban.user} was banned for {userban.reason}')


@bot.command(pass_context=True)
@has_permissions(kick_members=True)
async def kick(ctx, member: discord.Member, *reason):
    """kicks a user from the channel"""
    await log_action(ctx, action.kick, member.mention, reason)
    reason = ' '.join(reason)
    await ctx.guild.kick(member, reason=reason)
    # mutelog = mutelogs.get(ctx.guild, None)
    # if mutelog:
    #     if not reason:
    #         reason = ('No', 'Reason')
    #     await log_action(mutelog, action.kick, ctx.message.author.mention, member.mention, reason)


def message_repetition(message):
    message = drop_domains(message)  # drop the domains from any urls in the msssage
    message = drop_code_blocks(message)  # drop any code blocks in the message
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


# noinspection RegExpRedundantEscape
def drop_domains(message):
    pattern = re.compile(
        r'(?i)\b((?:https?://|www\d{0,3}[.]|[a-z0-9.\-]+[.][a-z]{2,4}/)(?:[^\s()<>]+|\(([^\s()<>]+|(\([^\s()<>]+\)))*\))+(?:\(([^\s()<>]+|(\([^\s()<>]+\)))*\)|[^\s`!()\[\]{};:\'".,<>?\xab\xbb\u201c\u201d\u2018\u2019]))')
    matches = re.findall(pattern, message)
    matches2 = ['/'.join((x[0].split('/'))[:3]) for x in matches]
    for match in matches2:
        message = re.sub(match, '', message)
    return message


def drop_code_blocks(message):
    pattern = re.compile(r'```.*```')
    matches = re.findall(pattern, message)
    for match in matches:
        message = re.sub(match, '', message)
    return message


@bot.command(pass_context=True)
@has_permissions(manage_channels=True)
async def ignore(ctx, channel=None):
    """marks a channel as ignored by Anti-Spam
    ignored channels are not monitored at all."""
    if channel is None:
        ctx.send('channel is a required argument')
    channel = [x.id for x in bot.get_all_channels() if x.name == channel and x.guild.id == ctx.guild.id]
    if channel:
        channel = channel[0]

    sql_c.execute('insert or replace into ignoring (guild, channel) values (?, ?)', (ctx.guild.id, str(channel),))
    database.commit()


@bot.command(pass_context=True)
@has_permissions(manage_channels=True)
async def ignoreall(ctx, channel=None):
    """marks all channels as ignored by Anti-Spam
    ignored channels are not monitored at all."""
    channels = [x.id for x in bot.get_all_channels() if x.guild.id == ctx.guild.id]
    for channel in channels:
        sql_c.execute('insert or replace into ignoring (guild, channel) values (?, ?)', (ctx.guild.id, str(channel),))
        database.commit()


@bot.command(pass_context=True)
@has_permissions(manage_channels=True)
async def watchall(ctx, channel=None):
    """marks all channels as ignored by Anti-Spam
    ignored channels are not monitored at all."""
    channels = [x.id for x in bot.get_all_channels() if x.guild.id == ctx.guild.id]
    for channel in channels:
        sql_c.execute('delete from ignoring where guild=? and channel=?', (ctx.guild.id, channel,))
        database.commit()


@bot.command(pass_context=True)
@has_permissions(manage_channels=True)
async def watch(ctx, channel=None):
    """marks an ignored channel as being watched"""
    if channel is None:
        ctx.send('channel is a required argument')
    channel = [x.id for x in bot.get_all_channels() if x.name == channel and x.guild.id == ctx.guild.id]
    if channel:
        channel = channel[0]
    sql_c.execute('delete from ignoring where guild=? and channel=?', (ctx.guild.id, channel,))
    database.commit()


@bot.command(pass_context=True)
async def expire(ctx, member: discord.Member):
    """gets the current mute state of the user across all channels on the server"""
    author = member.mention
    channels = read_messages(author)
#    channels = [x for x in channels if channels[2] > 0]
    embed = discord.Embed(title=member.name + '\'s escalation state per channel')
    now = int(datetime.datetime.utcnow().timestamp())
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
                s += 'Expires %ds' % expire
        embed.add_field(name=channel.name, value=s)
    await ctx.send(embed=embed)


@bot.command(pass_context=True)
@has_permissions(manage_channels=True)
async def ignored(ctx):
    """outputs a list of the channels currently being ignored by Anti-Spam"""
    ignore = sql_c.execute('select * from ignoring where guild=?', (ctx.guild.id,)).fetchall()
    ignore = [(bot.get_channel(int(x[1]))).name for x in ignore]
    if ignore:
        ignore = ', '.join(ignore)
    else:
        ignore = 'None'
    await ctx.send('The following channels are not monitored for anti_spam: ' + ignore)


@bot.command(pass_context=True)
@has_permissions(manage_channels=True)
async def terminate(ctx):
    import sys
    """terminates the bot's process with sys.exit(1)"""
    sys.exit(1)


@bot.command(pass_context=True)
@has_permissions(manage_channels=True)
async def warn(ctx, parameter=None):
    """toggles or shows the current warnings only setting
    parameter is expected to be the strings 'on' or 'off', case insensitive"""
    global warn_only
    if not parameter:
        if warn_only:
            await ctx.send('Action will not be taken for infractions, only warnings are given.')
        else:
            await ctx.send('Action will be taken for infractions.')
    else:
        if parameter.upper() == 'ON':
            warn_only = True
            await ctx.send('WARN_ONLY is now enabled.')
        elif parameter.upper() == 'OFF':
            warn_only = False
            await ctx.send('WARN_ONLY is now disabled.  Penalties may be applied for infractions.')
        else:
            await ctx.send(f'I don\'t know if {parameter} is supposed to be "on" or "off"')



bot.run(token())

