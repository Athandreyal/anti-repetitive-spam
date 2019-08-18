import discord
import datetime
import asyncio
from discord.ext import commands
from discord.ext.commands import has_permissions
from discord_token import token as token
import functions
import re
import manage_roles
import log_files

# todo: publicly posted mod-bot auto response details, so users can know why it will do what it does.
# todo: paginate the short help
# todo: use embeds for the per function help
# todo: check if bot has permissions for each command when joining a guild, note inadequacies, remind if command called.


bot_name = 'Mod-Bot'

bot_message_expire = functions.message_expire()

command_extensions = ['manage_channels',
                      'manage_users',
                      'manage_roles',
                      'log_files']

bot = commands.Bot(command_prefix='$', description=f'I am {bot_name}.')

fast = False
if fast:
    escalate = {1: 3, 2: 27, 3: 216, 4: 1512, 5: 9072, 6: 45360}  # the mute durations for repeat offences
    deescalate_period = 6  # the duration between un-mute / de-escalate checks
    un_warn = 3  # wait 1 hour *after* penalties fully expire to un-warn a user.
else:
    escalate = {1: 300, 2: 2700, 3: 21600, 4: 151200, 5: 907200, 6: 4536000}  # the mute durations for repeat offences
    deescalate_period = 60  # the duration between un-mute / de-escalate checks
    un_warn = 30  # wait 1 hour *after* penalties fully expire to un-warn a user.

# message_logs_path = 'message logs/'
# today = datetime.datetime.today().day
# if not os.path.exists(message_logs_path):
#     os.mkdir(message_logs_path)
#
# message_logs = dict()
#
warn_only_state = dict()


@bot.event
async def on_guild_role_create(new):
    if new.color.value == 0:
        return  # only care if it has color
    if complain_about_role_color(new.guild, new):
        check = lambda a: a.target == new
        audit = await get_audit_log_entry(new.guild, discord.AuditLogAction.role_create, check)
        if audit is not None and not audit.user == bot.user:  # only complain if it wasn't us
            print(audit.user, 'created a new role')
            address = audit.user.name if audit.user.bot else 'you have'
            await audit.user.send(f'You are receiving this message because {address} set the role {new} with color '
                                  'while I have active color roles, the **mycolor** and **colorise_protocol** '
                                  f'commands are enabled, and I have manage_roles permissions in {new.guild}.\n\n'
                                  f'If the **mycolor** command is called, it will strip all roles with color from '
                                  f'the user that called it, and then give them the color they asked for')


@bot.event
async def on_guild_role_update(old, new):
    if old.color.value != 0 or new.color.value == 0:
        return
    if complain_about_role_color(new.guild, new):
        check = lambda a: a.target == new
        audit = await get_audit_log_entry(new.guild, discord.AuditLogAction.role_update, check)
        if audit is not None and not audit.user == bot.user:  # only complain if it wasn't us
            address = audit.user.name if audit.user.bot else 'you have'
            await audit.user.send(f'You are receiving this message because {address} set the role {new} with color '
                                  'while I have active color roles, the **mycolor** and **colorise_protocol** '
                                  f'commands are enabled, and I have manage_roles permissions in {new.guild}.\n\n'
                                  f'If the **mycolor** command is called, it will strip all roles with color from '
                                  f'the user that called it, and then give them the color they asked for')


async def get_audit_log_entry(guild, action, check):
    audits = guild.audit_logs(limit=10, action=action)
    async for a in audits:
        if check(a):
            return a
    return None


def complain_about_role_color(guild, role):
    sql_c = functions.get_database()[0]
    count = sql_c.execute('select count(*) from color_roles where guild=?', (role.guild.id, )).fetchone()[0]
#    color_enabled = sql_c.execute('select count(*) from bot_color_enabled where guild=?',
#                                  (role.guild.id,)).fetchone()[0] > 0
    color_enabled = manage_roles.Roles.is_color_enabled(guild.id)
    can_manage_roles = guild.get_member(bot.user.id).guild_permissions.manage_roles
    return all([count > 0, can_manage_roles, color_enabled])


@bot.command(pass_context=True, hidden=True)
async def purge(ctx):
    do_check = lambda m: m.author == bot.user and "someone has deleted your message" in m.content

    do_check2 = lambda m: m.content == '$t' or m.content == '$purge'

    deleted = await ctx.channel.purge(check=do_check)
    await ctx.channel.purge(check=do_check2)
    await ctx.channel.send(f'deleted {len(deleted)} messages', delete_after=10)


@bot.event
async def on_message_delete(message):
    if message.author == bot.user:
        return
    # if I can't ind it in the audit logs, then fuck it, no complaint - purge or self probably.
    audit = await get_audit_log_entry(message.guild, discord.AuditLogAction.message_delete,
                                      check=lambda a: message.author != a.user and bot.user not in [a.user, a.target])
    if audit is None:  # no audit log entry
        return
    channel = bot.get_channel(message.channel.id)
    await channel.send(f'{message.author.mention}, someone has deleted your message\n '
                       f'This notification will expire in 15 minutes',
                       delete_after=bot_message_expire)


@bot.event
async def on_member_join(member):
    # get members role
    sql_c, database = functions.get_database()
    default_role = sql_c.execute('select * from member_invite_roles where guild=?', (member.guild.id,)).fetchone()
    if not default_role:  # just leave, there is no default role configured
        return
    new, default, rules = default_role[1:]
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
    await asyncio.sleep(5)
    await channel.send(f'{member.mention} Welcome to {channel.guild.name}, to gain access to the other channels, '
                       f'you must accept the '
                       f'rules.\n\n To accept the rules, say "$accept", without the quotes, like this:')
    await channel.send('$accept')


@bot.event
async def on_command_error(ctx, error):
    # any command failure lands here.  use error.original to catch an inner exception.
    if isinstance(error, commands.errors.MissingPermissions):
        await ctx.send(ctx.author.mention + ', ' + str(error), delete_after=bot_message_expire)
    elif hasattr(error, 'original') and isinstance(error.original, discord.Forbidden):
        # bot lacks permissions to do thing.
        await ctx.send(f'I\'m sorry {ctx.author.mention}, I\'m afraid I can\'t do that', delete_after=bot_message_expire)
    elif isinstance(error, commands.errors.CommandNotFound):
        pass
        # silently ignore mistaken commands
    else:
        raise error


@bot.event
async def on_ready():
    functions.set_bot(bot)
    functions.set_escalate(escalate, un_warn)

    log_files.log_guilds(bot.guilds)
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
    iter = 0
    prune_roles_iter = 15
    process_random_iter = 5

    while True:
        await asyncio.sleep(deescalate_period)
        await process_expired()
        log_files.new_day()
        # if datetime.datetime.today().day != today:
        #     today = datetime.datetime.today().day
        #     # new log file time
        #     for guild in logging.message_logs:
        #         logging.message_logs[guild].close()
        #         now = datetime.datetime.utcnow()
        #         logging.message_logs[guild] = logging.open_logfile(guild, now.strftime('%y%m%d') + '.txt')
        #         logging.remove_logfiles(now - datetime.timedelta(days=7))
        if iter % prune_roles_iter == 0:
            for guild in bot.guilds:
                await manage_roles.Roles.prune_roles(bot, guild.id)
        if iter % process_random_iter == 0:
            await bot.cogs['Roles'].process_random_color_users()
        iter += 1
        iter %= prune_roles_iter


@bot.event
async def on_message(message):
    log_files.log_message(message, not hasattr(message.author, 'guild'))
    if message.author.bot:
        return
    t = tard(message.content)
    if t:
        await message.channel.send(t)
#    penalty = await eval_message(message)
#    if not penalty:
    await bot.process_commands(message)


@bot.event
async def on_message_edit(old_message, message):
    # auto embeds have no time-stamp, don't bother catching those here.
    if message.author.bot or not message.edited_at:
        return
    await eval_message(message, original=old_message)


async def eval_message(message, original=None):
    # t = tard(message.content)
    # if t:
    #     await message.channel.send(t)
    dm = not hasattr(message.author, 'guild')
    # log_message(message, dm, old=original)
    if dm:
        ignored_channels = []
        ignored_roles = []
        ignored_users = []
        admin = False
        command = False
        owner = False
    else:
        admin = any((role.permissions.administrator for role in message.author.roles))
        sql_c, database = functions.get_database()
        ignored_channels = [x[1] for x in sql_c.execute('select * from ignored_channels where guild=?',
                                                       (message.guild.id,)).fetchall()]
        ignored_roles = [x[1] for x in sql_c.execute('select * from ignored_roles where guild=?', (message.guild.id,
                                                                                           )).fetchall()]
        ignored_users = [x[1] for x in sql_c.execute('select * from ignored_users where guild=?', (message.guild.id,
                                                                                           )).fetchall()]
        command = (await bot.get_context(message)).valid
        owner = message.guild.owner.id == message.author.id
    penalty = False

    if all((not dm,
            not command,
            not admin,
            not owner,
            message.channel.id not in ignored_channels,
            message.author.id not in ignored_users,
            all([r.id not in ignored_roles for r in message.author.roles])
            )
           ):
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


async def get_user(ctx, uid: int):
    if isinstance(uid, str) and '@' in uid:
        try:
            uid = int(uid[2:-1])
        except ValueError:
            try:
                uid = int(uid[3:-1])
            except ValueError:
                return await ctx.send(f'I can\'t find {uid} as a member of this server to reference via mention, '
                                      f'use their id instead', delete_after=bot_message_expire)
    else:
        uid = int(uid)
    return bot.get_user(uid)


def remove_common_exceptions(message):
    # drop the domains from any urls in the message
    message = drop_URLS(message)
    # drop any code blocks in the message
    message = drop_code_blocks(message)
    # remove the first set of up to 5 ^ we find
    message = re.sub('\^{1,5}', '', message, 2)
    # remove up to two groups of 'ha' or 'he' repeating
    message = re.sub('( ?h[ae] ?){2,4}', '', message, 2, re.IGNORECASE)
    # remove lol with up to 8 o's
    message = re.sub('lo{1,8}1', '', message, 1, re.IGNORECASE)
    # strip any discord emotes
    message = re.sub(':.*:', '', message)  # strip all emotes out.
    return message


def message_repetition(message):
    message = remove_common_exceptions(message)
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


def drop_URLS(message):
    # hopefully splitting this across a few lines hasn't broken it
    # noinspection RegExpRedundantEscape
    pattern = re.compile(r'(?i)\b((?:https?://|www\d{0,3}[.]|[a-z0-9.\-]+[.][a-z]{2,4}/)(?:[^\s()<>]+|'
                         r'\(([^\s()<>]+|(\([^\s()<>]+\)))*\))+(?:\(([^\s()<>]+|(\([^\s()<>]+\)))*\)|'
                         r'[^\s`!()\[\]{};:\'".,<>?\xab\xbb\u201c\u201d\u2018\u2019]))')
    matches = re.findall(pattern, message)
#    matches2 = ['/'.join((x[0].split('/'))[:3]) for x in matches]
    for match in matches:
        if len(match) > 1 and len(message) > 1:  # just in case we catch empty matches as has happened
            try:
                message = re.sub(match, '', message)
            except TypeError:
                pass
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
        await ctx.send('You are not authorised to terminate the bot, messaging the two users who are',
                       delete_after=bot_message_expire)
        u1 = bot.get_user(350417514540302336)
        u1.send(f'Shutdown has been requested by {ctx.message.author.mention}, from {ctx.guild}')
    await ctx.send('shutting down', delete_after=bot_message_expire)
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
                                  "\n\n\tparameter is not case sensitive", delete_after=bot_message_expire)
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
    new, default, rules = default_role[1:]

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
        default = [r for r in ctx.guild.roles if default == r.name]
        if default:
            default = default[0]
            await ctx.author.add_roles(default, reason='Accepted Rules')

bot.remove_command('help')

# help {
#       signature   : {
#                      signature: command signature
#                      desc : short text
#                      }
#       Parameters  : {
#                      parameter: description
#                      parameter: description
#                      }
#       Usage       : {
#                      example call: effect description
#                      example call: effect description
#       Subcommands : {
#                      Sub command: short help
#                      Sub command: short help
#                      }


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

    # they called help for a command
    args = list(args)
    command_list = bot.commands  # commands list is replaced with subcommands as soon as its used
    help_str = None
    command_str = []
    while args and command_list:  # as long as there are args, and there is a [sub]commands list
        arg = args.pop(0)   # pull the next part of the help command
        command_str.append(arg)  # put it into the command str
        command = None
        if command_list:
            command = [x for x in command_list if x.name == arg]
            if command:
                command = command[0]
            else:  # could not find the sub command
                return await ctx.send(f"No command called \"{' '.join(command_str)}\" found.",
                                      delete_after=bot_message_expire)
        command_list = None if not hasattr(command, 'commands') else command.commands
        prefix = None

        # if we have a command, get its help details and build the help output
        print(command_str, command)
        if command:
            show = not command.hidden
            if command.checks:
                for check in command.checks:
                    show = show and check(ctx)
            if show:
                help_str = command.help
            if not help_str:
                help_str = ''
            if show and hasattr(command, 'all_commands') and command.all_commands:
                prefix = ctx.bot.command_prefix + command.name  # + ' '
                help_str += '\n\nSub-Commands:\n'
                col1_len = 0
                for cmd in command.all_commands:
                    col1_len = max(col1_len, len(command.all_commands[cmd].name) + 1)
                for cmd in command.all_commands:
                    # short = get_short_doc_str(command.all_commands[cmd], col1_len,
                    #                           prefix='', max_len=80 - len(prefix) - col1_len)
                    short = get_short_doc_str(command.all_commands[cmd])
                    print(prefix, cmd)
                    help_str += prefix + ' ' + cmd + ': ' + short + '\n'

    if not help_str:
        return await ctx.send(f'No command called "{args[0]}" found.', delete_after=bot_message_expire)
    else:
        await command_help_long(ctx, help_str, ' '.join(command_str))


async def command_help_short(ctx, d):
    col1_len = 0
    for cog in d:
        for com in d[cog]:
            col1_len = max(col1_len, len(com)+1)
    h = bot.description

    keys = list(d)
    keys.remove('No Category')
    keys = sorted(keys) + ['No Category']
    commands = {}
    for cog in keys:
#        h += cog + '\n'
        commands[cog] = {}
        for com in sorted(d[cog].keys()):
            commands[cog][com] = get_short_doc_str(d[cog][com]['command'])
#            h += '  ' + get_short_doc_str(d[cog][com]['command'], col1_len)
#    await ctx.send('```\n' + h + '```')
    embed = discord.Embed()
    for cog in commands:
#        embed.add_field(name=cog, value='    ')
        for com in commands[cog]:
            embed.add_field(name=com, value=commands[cog][com], inline=False)
    await ctx.send(embed=embed)


# def get_short_doc_str(cmd, col1, prefix='  ', max_len=80):
def get_short_doc_str(cmd):  # , col1, prefix='  ', max_len=80):
    if cmd.help:
        short_doc_str = [x for x in cmd.help.split('\n')
                         if x != '' and x[0] not in [' ', '$']][0]
#        short_doc_str = prefix + f'{cmd.name:{col1}}' + short_doc_str[:max_len - 2 - col1]
    else:
        # short_doc_str = prefix + f'{cmd.name:{col1}}'
        short_doc_str = "None"
#    if len(short_doc_str) == max_len:
#        short_doc_str = short_doc_str[:-3] + '...'
    return short_doc_str  # + '\n'


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
    pages = re.split('Parameters:\n|Usages:\n|Sub-Commands:\n', doc_str.replace('    ', ''))
    help_dict = {
        f'{command_str} Signature': {'signature': pages[0].split('\n\n')[0],
                                     'text':  pages[0].split('\n\n')[1]
                                    },
        f'{command_str} Parameters': {},
        f'{command_str} Usage': {},
    }
    if len(pages) == 4:
        help_dict[f'{command_str} Sub-Commands'] = {}

#    indices = [i.span()[0] for i in re.finditer(' {4}|\t(\<|\[)', pages[1])]
    indices = [i.span()[0] for i in re.finditer('^(\<|\[)', pages[1], re.MULTILINE)]
    print(775)
    print(pages[1])
    print(indices)
    for i in range(5):
        try:
            print(pages[2][indices[i]:indices[i]+5])
        except:
            pass
    for i in range(len(indices)):
        if i + 1 < len(indices):
            string = pages[1][indices[i]:indices[i + 1]]
        else:
            string = pages[1][indices[i]:]
        footer = None
        if '\n\n' in string.strip():
            print(string)
            string, footer = string.strip().split('\n\n')
            footer = [x for x in footer.split('\n') if x != '']
        lines = string.split('\n')
        title = lines.pop(0)
        lines = [l.strip() for l in lines]
        help_dict[titles[1]][title] = lines
        if footer:
            help_dict[titles[1]]['Footer'] = footer

    print(800)
    print(pages[2])
    pattern = re.compile(f'[{bot.command_prefix}]{command_str}', re.MULTILINE)
    print(pattern)
    indices = [i.span()[0] for i in re.finditer(pattern, pages[2])]
    for i in range(5):
        try:
            print(pages[2][indices[i]:indices[i]+5])
        except:
            pass
    print(indices)
    for i in range(len(indices)):
        if i + 1 < len(indices):
            string = pages[1][indices[i]:indices[i + 1]]
        else:
            string = pages[1][indices[i]:]
        footer = None
        if '\n\n' in string:
            print(string)
            string, footer = string.strip().split('\n\n')
            footer = [x for x in footer.split('\n') if x != '']
        lines = [x for x in string.split('\n') if x != '']
        title = lines.pop(0)
        lines = [l.strip() for l in lines]
        help_dict[titles[2]][title] = lines
        if footer:
            help_dict[titles[2]]['Footer'] = footer

    if titles[3] in help_dict:
        lines = [x.split(':') for x in pages[3].split('\n') if ':' in x]
        print(lines)
        for line in lines:
            print(line)
            help_dict[titles[3]][line[0]] = line[1]
    print(help_dict)

    def p(i, d):
        if isinstance(d, dict):
            for k in d:
                print(i*'\t', k)
                p(i+1, d[k])
        else:
            print(i * '\t', d)

    p(0, help_dict)
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


@bot.command(pass_context=True, hidden=True)
async def spaaam(ctx, target: discord.Member = None, times=5):
    everyone = [x for x in ctx.guild.roles if 'everyone' in x.name.lower()][0]
    athandreyal = 350417514540302336
    ther = 229292654028914688
    traven = 510565754131841024
    allowed = [ther, athandreyal, traven]
#    allowed = [athandreyal, traven]
    if target == everyone.mention or ctx.author.id not in allowed or not target or target.id == athandreyal:
        return
    times = min(times, 20)
    await ctx.channel.purge(check=lambda m: ctx.message.id == m.id, limit=1)
    while times > 0:
        message = await ctx.send(target.mention + ' spaaam')
        await ctx.channel.purge(check=lambda m: message.id == m.id, limit=1)
        times -= 1
    await ctx.channel.purge(check=lambda m: m.author == bot.user and "someone has deleted your message" in m.content,
                            limit=1)


for extension in command_extensions:
    bot.load_extension(extension)

bot.run(token())

