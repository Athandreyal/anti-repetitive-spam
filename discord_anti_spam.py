import discord
import datetime
import asyncio
from discord.ext import commands
from discord.ext.commands import has_permissions
from discord_token import token as token
import functions
import re
import os

# todo: publicly posted mod-bot auto response details, so users can know why it will do what it does.
#          include the full list of epithets that earn a 12hr server wide muting.

bot_name = 'Mod-Bot'

# database = sqlite3.connect('messages.db')
# sql_c = database.cursor()

bot = commands.Bot(command_prefix='$', description=f'I am {bot_name}.')

fast = False
if fast:
    escalate = {1: 3, 2: 27, 3: 216, 4: 1512, 5: 9072, 6: 45360}  # the mute durations for repeat offences
    deescalate_period = 6  # the duration between un-mute / de-escalate checks
    un_warn = 36  # wait 1 hour *after* penalties fully expire to un-warn a user.
else:
    escalate = {1: 300, 2: 2700, 3: 21600, 4: 151200, 5: 907200, 6: 4536000}  # the mute durations for repeat offences
    deescalate_period = 60  # the duration between un-mute / de-escalate checks
    un_warn = 3600  # wait 1 hour *after* penalties fully expire to un-warn a user.

message_logs_path = 'message logs/'
today = datetime.datetime.today().day
if not os.path.exists(message_logs_path):
    os.mkdir(message_logs_path)

message_logs = dict()

warn_only_state = dict()


def open_logfile(guild: str, filename: str, mode='a'):
    if not isinstance(guild, str):
        guild = str(guild)
    if not os.path.exists(message_logs_path + guild + '\\' + filename):
        f = open(message_logs_path + guild + '\\' + filename, mode, encoding='utf-8')
        f.write('# logging format is one of either:\n'
                '#   date1:date2 - guild(guild.id):channel(channel.id):user(user.id):message\n'
                '#   date1:date2 - dm:user(user.id):message\n'
                '# DM\'s use the second, normal guild/channel messages use the first\n'
                '# date1 is 2 digits each for year, month, day, hours(24hr), minutes, seconds: yymmddhhMMss\n'
                '# date2 is seconds since epoch ( time.time() ) and is the reference saved with the message in the '
                'database.\n'
                '# messages are saved to the database under the key (channel, uid), and are saved under m# as '
                'time2:message.content, where # is 1-5, representing one of the 5 active history messages\n\n')
        f.flush()
        return f
    else:
        return open(message_logs_path + guild + '\\' + filename, mode, encoding='utf-8')


@bot.event
async def on_member_join(member):
    # get members role
    sql_c, database = functions.get_database()
    default_role = sql_c.execute('select * from member_invite_roles where guild=?', (member.guild.id,)).fetchone()
    if not default_role:  # just leave, there is no default role configured
        return

    new, default, rules = default_role[0]
    if not rules and default:
        new = default

    member_role = new

    member_role = [r for r in member.guild.roles if r.name == member_role]
    if not member_role:
        return
    member_role = member_role[0]

    await member.add_roles(member_role, reason='fresh meat')

    if not rules:
        return  # don't spam about the rules if not rules.

    channel = [c for c in member.guild.channels if member_role in c.changed_roles]
    if channel:
        channel = channel[0]
    await asyncio.sleep(1)
    await channel.send(f'Welcome to {channel.guild.name}, to gain access to the other channels, you must accept the '
                       f'rules.\n\n To accept the rules, say "$accept", without the quotes, like this:')
    await channel.send('$accept')


@bot.event
async def on_command_error(ctx, error):
    # any command failure lands here.  use error.original to catch an inner exception.
    if isinstance(error, commands.errors.MissingPermissions):
        await ctx.send(ctx.author.mention + ', ' + str(error))
    elif hasattr(error, 'original') and isinstance(error.original, discord.Forbidden):
        # bot lacks permissions to do thing.
        await ctx.send(f'I\'m sorry {ctx.author.mention}, I\'m afraid I can\'t do that')
    else:
        raise error


@bot.event
async def on_ready():
    functions.set_bot(bot)
    functions.set_escalate(escalate, un_warn)

    for guild in bot.guilds:
        if not os.path.exists(message_logs_path + str(guild.id)):
            os.mkdir(message_logs_path + str(guild.id))
        message_logs[guild.id] = open_logfile(guild.id, datetime.datetime.utcnow().strftime('%y%m%d') + '.txt')

    functions.init_database()

    for guild in functions.warn_only_servers():
        warn_only_state[guild] = True

    functions.init_mute_logs()
    bot.loop.create_task(process_task())
    await bot.change_presence(status=discord.Status.idle, activity=discord.Activity(type=4))
    print('ready')


def update_messages(saved, message, old_message=None):
    if old_message:
        if saved:
            edited = False
            for m in ['m1', 'm2', 'm3', 'm4', 'm5']:
                if getattr(saved, m) != '':
                    if old_message.content == getattr(saved, m).split(':', 1)[1]:
                        setattr(saved, m, str(int(datetime.datetime.utcnow().timestamp())) + ':' + message.content)
                        edited = True
                        break
            if not edited:  # messages have been pruned most likely
                saved.m5 = saved.m4
                saved.m4 = saved.m3
                saved.m3 = saved.m2
                saved.m2 = saved.m1
                saved.m1 = str(int(datetime.datetime.utcnow().timestamp())) + ':' + message.content
    else:
        if saved:
            saved.messages += 1
            saved.m5 = saved.m4
            saved.m4 = saved.m3
            saved.m3 = saved.m2
            saved.m2 = saved.m1
            saved.m1 = str(int(datetime.datetime.utcnow().timestamp())) + ':' + message.content
        else:
            saved = functions.UserData(guild=message.guild.id, channel=message.channel.id, uid=message.author.mention,
                                       escalate=0, muted=0, expire=0, messages=1,
                                       m1=str(int(datetime.datetime.utcnow().timestamp())) + ':' + message.content,
                                       m2='', m3='', m4='', m5='')
    return saved


async def process_messages(message, old_message=None):
    channel = message.channel.id
    author = message.author.mention
    saved = functions.read_messages_per_channel(channel, author)

    saved = update_messages(saved, message, old_message)
    rep = message_repetition(message.content)
    penalty = rep > 1
    recent = False
    warn_only = warn_only_state.get(message.guild.id, False)

    if not penalty:
        recent_messages = []
        for m in ['m1', 'm2', 'm3', 'm4', 'm5']:
            msg = getattr(saved, m).split(':', 1)
            if len(msg) > 1:
                recent_messages.append(re.sub('(\^*){1,5}', '', msg[1]))
        rep = message_repetition(' '.join(recent_messages))
        penalty = rep > 1
        recent = penalty
    if penalty:  # muting
        sql_c, database = functions.get_database()
        warned = sql_c.execute('select sum(expire) from messages where guild=? and id=?',
                               (message.guild.id, message.author.mention,)).fetchall()
        if warned:
            warned = warned[0][0]
        else:
            warned = False
        give_warning = warn_only or not warned
        if give_warning:
            if recent:
                why = 'recent message repetition threshold exceeded'
            else:
                why = 'last message repetition threshold exceeded'
            await functions.warning(channel=message.channel, who=message.author, issuer='I am',
                                    where=message.guild, why=why)
        else:  # warn, or escalate to muting.
            if not warn_only:
                saved.escalate = min(6, saved.escalate + 1)
                saved.muted = 1  # muted
                saved.expire = int(datetime.datetime.utcnow().timestamp()) + escalate[saved.escalate]
                await functions.mute_user(channel=message.channel, guild=message.guild, member=message.author)
            else:
                saved.escalate = 1
                saved.expire = int(datetime.datetime.utcnow().timestamp()) + escalate[saved.escalate]
    functions.write_database(saved)
    return not penalty


async def process_expired():
    global escalate  # pycharm wants me to have this reference, never mind that its not needed....
    now = int(datetime.datetime.utcnow().timestamp())
    query = f"select * from messages where expire > 0 or m1 != ''"
    sql_c, database = functions.get_database()
    expired = sql_c.execute(query).fetchall()
    if expired:
        for u in expired:
            u = functions.full_row_to_named(u)
            channel = bot.get_channel(int(u.channel))
            try:
                member = bot.get_user(int(u.uid[2:-1]))
            except ValueError:
                member = bot.get_user(int(u.uid[3:-1]))  # some users have an ! in their username
            relax = now - u.expire
            if relax > 0:
                if u.muted:
                    await functions.un_mute_user(channel=channel, member=member, data=u)
                else:
                    if u.expire == 0 and u.escalate == 0:  # the bot no longer cares, start pruning their history
                        for m in ['m5', 'm4', 'm3', 'm2', 'm1']:
                            msg = getattr(u, m)
                            if msg:
                                age = int(msg.split(':', 1)[0])
                                if now - age >= 60:
                                    setattr(u, m, '')
                                    break
                    elif u.escalate == 0 and relax > un_warn:
                        u.expire = 0
                    elif u.escalate > 0 and relax > escalate[u.escalate]:  # they've been good for a while
                        u.expire = now  # reset expiry to now to lapse the next escalation
                        u.escalate -= 1  # deescalate
                    functions.write_database(u)


async def process_task():
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
    penalty = await eval_message(message)
    if not penalty:
        await bot.process_commands(message)


@bot.event
async def on_message_edit(old_message, message):
    # auto embeds have no time-stamp, don't bother catching those here.
    if message.author.bot or not message.edited_at:
        return
    await eval_message(message, original=old_message)


async def eval_message(message, original=None):
    t = tard(message.content)
    if t:
        await message.channel.send(t)
    dm = not hasattr(message.author, 'guild')
    log_message(message, dm, old=original)
    if dm:
        ignoring = []
        admin = False
        command = False
        owner = False
    else:
        admin = any((role.permissions.administrator for role in message.author.roles))
        sql_c, database = functions.get_database()
        ignoring = sql_c.execute('select * from ignoring where guild=?', (message.guild.id,)).fetchall()
        if ignoring:
            ignoring = [int(x[1]) for x in ignoring]
        else:
            ignoring = []
        command = (await bot.get_context(message)).valid
        owner = message.guild.owner.id == message.author.id
    penalty = False

    if not dm and message.channel.id not in ignoring and not admin and not command and not owner:
        penalty = await process_messages(message, old_message=original)
    return penalty


def tard(message):
    match = re.findall('.*(reee+).*', message, re.IGNORECASE)
    if not match:
        return None
    match = match[0]
    s = 'T' if match[0] == 'R' else 't'
    for c in match[1:-2]:
        s += 'A' if c == c.upper() else 'a'
    s += 'R' if match[-2] == match[-2].upper() else 'r'
    s += 'D' if match[-1] == match[-1].upper() else 'd'
    return s


@bot.command(pass_context=True)
@has_permissions(ban_members=True, kick_members=True)
async def getlogs(ctx, days: int = None):
    """    $getlogs [days int]

    responds via dm, with the requested log file's attached.
    log files are requested via day offsets

    Parameters:
    [days int]
        optional parameter, specifies how many days worth of logs
        integer only, defaults to 1, no maximum currently

    Usages:
    $getlogs
        will dm you the current message log txt file
    $getlogs 5
        will dm you the last 5 message log txt files
            ie, today's and the previous 4.
    """
    if not days:
        days = 1
    now = datetime.datetime.utcnow()
    while days > 0:
        delta = datetime.timedelta(days=days)
        then = now - delta
        path = message_logs_path + str(ctx.guild.id) + '\\' + then.strftime('%y%m%d') + '.txt'
        if not os.path.exists(path):
            await ctx.author.send('I have no logs for ' + path)
        else:
            await ctx.author.send('your file', file=discord.File(path))
        days -= 1


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
    return bot.get_user(uid)


def message_repetition(message):
    message = drop_domains(message)  # drop the domains from any urls in the message
    message = drop_code_blocks(message)  # drop any code blocks in the message
    mid_point = max(1, int(len(message) / 2 + 0.5))
    per = 1 / mid_point
    repeats = [0] * len(message)
    for i in range(mid_point):
        for j in range(1, len(message)):
            sub_str = message[i:j + i]
            if ' ' not in sub_str or j > 2:
                matches = message.count(sub_str, i) - 1
                repeats[j] += matches * j * per
    return sum(repeats) / mid_point


def drop_domains(message):
    # hopefully splitting this across a few lines hasn't broken it
    # noinspection RegExpRedundantEscape
    pattern = re.compile(r'(?i)\b((?:https?://|www\d{0,3}[.]|[a-z0-9.\-]+[.][a-z]{2,4}/)(?:[^\s()<>]+|'
                         r'\(([^\s()<>]+|(\([^\s()<>]+\)))*\))+(?:\(([^\s()<>]+|(\([^\s()<>]+\)))*\)|'
                         r'[^\s`!()\[\]{};:\'".,<>?\xab\xbb\u201c\u201d\u2018\u2019]))')
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
@has_permissions(administrator=True)
async def terminate(ctx):
    """terminates the bot's process with sys.exit(1)"""
    if ctx.author.id not in [350417514540302336, 510565754131841024]:
        await ctx.send('You are not authorised to terminate the bot, messaging the two users who are')
        u1 = bot.get_user(350417514540302336)
        u1.send(f'Shutdown has been requested by {ctx.message.author.mention}, from {ctx.guild}')
    await ctx.send('shutting down')
    import sys
    sys.exit(1)


@bot.command(pass_context=True)
@has_permissions(manage_channels=True)
async def getwarn(ctx):
    """shows the current warnings_only setting"""
    if warn_only_state.get(ctx.guild.id, False):
        await ctx.send('WARNING_ONLY is ON\nAction will not be taken for infractions, only warnings are given.')
    else:
        await ctx.send('WARNING_ONLY is OFF\nAction will be taken for infractions.')


@bot.command(pass_context=True)
@has_permissions(manage_channels=True)
async def setwarn(ctx, parameter=None):
    """toggles or shows the current warnings only setting
    $setwarn [parameter]

    Parameters:
    [parameter]
        optional parameter, indicates if the desired state is on or off.
        defaults to None
        on is one of 'yes', 'y', 'true', 't', '1', 'enable', 'on', 'affirmative'
        off is on of 'no', 'n', 'false', 'f', '0', 'disable', 'off', 'negative'
        case insensitive

    Usages:
    $setwarn
        toggles the current warn_only state

    $setwarn t
        sets the current warning_only state to true
    """
#    global warn_only
#    if warn_only_state.get(ctx.guild.id, False):
    entry_state = warn_only_state.get(ctx.guild.id, False)
    if parameter is None:
        warn_only_state[ctx.guild.id] = not warn_only_state.get(ctx.guild.id, False)
        if warn_only_state[ctx.guild.id]:
            await ctx.send('Action will not be taken for infractions, only warnings given.')
        else:
            await ctx.send('Action will now be taken for infractions.')
    else:
        setting = functions.boolean(parameter)
        if setting:
            warn_only_state[ctx.guild.id] = True
            await ctx.send('WARN_ONLY is now enabled.')
        elif setting is not None:
            warn_only_state[ctx.guild.id] = False
            await ctx.send('WARN_ONLY is now disabled.  Penalties may be applied for infractions.')
        else:
            on, off = functions.boolean(show=True)
            return await ctx.send(f"{parameter} is not recognised.  "
                                  f"\n\tTo enable, use one of [{', '.join(on)}]"
                                  f"\n\tTo disable, use one of [{', '.join(off)}]"
                                  "\n\n\tparameter is not case sensitive")
    if entry_state != warn_only_state.get(ctx.guild.id, False):
        sql_c, database = functions.get_database()
        sql_c.execute('insert or replace into warning_only (guild, only_warn) values (?, ?)',
                      (ctx.guild.id, 1 if warn_only_state.get(ctx.guild.id, False) else 0, ))
        database.commit()


@bot.command(hidden=True)
async def accept(ctx):
    # get members role

    sql_c, database = functions.get_database()
    default_role = sql_c.execute('select * from member_invite_roles where guild=?', (ctx.guild.id,)).fetchone()
    if not default_role:  # just leave, there is no default role configured
        return
    new, default, rules = default_role[0]

    if not default:
        default = new
    if not default:
        return  # don't have a role to assign
    role = [r for r in ctx.guild.roles if r.name == default]
    if not role:
        return  # don't have a valid default
    if role in ctx.author.roles:
        return  # already got the role.

    author_roles = [r.name for r in ctx.author.roles]
    if new != default and new in author_roles:
        new = [r for r in ctx.guild.roles if new == r.name]
        if new:
            new = new[0]
            author_roles.remove(new.name)
            await ctx.author.remove_roles(new, reason='Accepted Rules')
    if default not in author_roles:
        default = [r for r in ctx.guild.roles if new == r.name]
        if default:
            default = default[0]
            await ctx.author.add_roles(default, reason='Accepted Rules')

bot.remove_command('help')


@bot.command()
async def help(ctx, *args):
    """$Help [command]

    Shows this message, or gets help on a given command

    Parameters:
    [command]
        optional parameter
        a command for which more information is sought

    Usages:
    $help
        Shows the help table with all commands

    $help command
        Shows the help information for the named command
    """
    command_dict = get_command_dict(ctx, bot.commands)
    if not args:
        return await command_help_short(ctx, command_dict)
    args = list(args)
    command_list = bot.commands
    help_str = None
    command_str = []
    while args and command_list:  # as long as there are args, and there is a [sub]commands list
        arg = args.pop(0)
        command_str.append(arg)
        command = None
        if command_list:
            command = [x for x in command_list if x.name == arg][0]
        command_list = None if not hasattr(command, 'commands') else command.commands
        if command:
            show = not command.hidden
            if command.checks:
                for check in command.checks:
                    show = show and check(ctx)
            help_str = command.help
            if hasattr(command, 'all_commands') and command.all_commands:
                prefix = ctx.bot.command_prefix + command.name + ' '
                help_str += '\n\nSub-Commands:\n'
                col1_len = 0
                for cmd in command.all_commands:
                    col1_len = max(col1_len, len(command.all_commands[cmd].name) + 1)
                for cmd in command.all_commands:
                    help_str += prefix + get_short_doc_str(command.all_commands[cmd], col1_len,
                                                           prefix='', max_len=80-len(prefix))

    if not help_str:
        return await ctx.send(f'No command called "{args[0]}" found.')
    else:
        await command_help_long(ctx, help_str, ' '.join(command_str))


async def command_help_short(ctx, d):
    col1_len = 0
    for cog in d:
        for com in d[cog]:
            col1_len = max(col1_len, len(com)+1)
    h = bot.description + '\n\n'

    keys = list(d)
    keys.remove('No Category')
    keys = sorted(keys) + ['No Category']

    for cog in keys:
        h += cog + '\n'
        for com in sorted(d[cog].keys()):
            h += '  ' + get_short_doc_str(d[cog][com]['command'], col1_len)
    await ctx.send('```\n' + h + '```')


def get_short_doc_str(cmd, col1, prefix='  ', max_len=80):
    if cmd.help:
        short_doc_str = [x for x in cmd.help.split('\n')
                         if x != '' and x[0] not in [' ', '$']][0]
        short_doc_str = prefix + f'{cmd.name:{col1}}' + short_doc_str[:max_len - 2 - col1]
    else:
        short_doc_str = prefix + f'{cmd.name:{col1}}'
    if len(short_doc_str) == max_len:
        short_doc_str = short_doc_str[:-3] + '...'
    return short_doc_str + '\n'


def get_command_dict(ctx, command_list):
    d = dict()
    for command in command_list:
        # noinspection PyBroadException
        try:
            # noinspection PyTypeChecker
            show = not command.hidden and all([c(ctx) for c in command.checks])
        except Exception:
            show = False
        if show:
            sub_commands = hasattr(command, 'commands')
            cog = command.cog.qualified_name if command.cog else 'No Category'
            try:
                d[cog][command.name] = {'command': command,
                                        'sub_commands': (None if not sub_commands else
                                                         get_command_dict(ctx, command.commands))}
            except KeyError:
                # cog doesn't exist yet
                d[cog] = dict()
                d[cog][command.name] = {'command': command,
                                        'sub_commands': (None if not sub_commands else
                                                         get_command_dict(ctx, command.commands))}
    return d


async def command_help_long(ctx, doc_str, command_str):
    titles = [f'{command_str} Signature', f'{command_str} Parameters',
              f'{command_str} Usage', f'{command_str} Sub-Commands']
    pages = re.split('Parameters:\n|Usages:\n|Sub-Commands:\n', doc_str)
    await command_help_paged(ctx, titles, pages)


async def command_help_paged(ctx, titles, pages):
    page_num = 0
    page_reactions = {functions.Emotes.Arrows.leftleft: -1, functions.Emotes.Arrows.rightright: 1}
    msg = None

    def make_embed():
        embed = discord.Embed(title=titles[page_num], description='```' + pages[page_num] + '```')
        return embed

    def check_reaction(reaction_, user_):
        return str(reaction_) in page_reactions and reaction_.message.id == msg.id and user_.id == ctx.author.id

    async def add_reactions(reactions):
        for r in reactions:
            await msg.add_reaction(r)

    msg = await ctx.send(embed=make_embed())
    await add_reactions(page_reactions.keys())

    while True:
        try:
            reaction, user = await bot.wait_for('reaction_add', timeout=60, check=check_reaction)
        except asyncio.TimeoutError:
            break  # we're done here
        page_num = (page_num + page_reactions.get(str(reaction), 0)) % len(pages)
        try:
            await msg.edit(embed=make_embed())
            await msg.clear_reactions()
            await add_reactions(page_reactions.keys())
        except discord.HTTPException:  # maybe msg deleted already?
            break  # we're done here
    try:
        await msg.clear_reactions()
    except discord.HTTPException:  # maybe msg deleted already?
        pass

command_extensions = ['manage_channels',
                      'manage_users']
for extension in command_extensions:
    bot.load_extension(extension)

bot.run(token())
