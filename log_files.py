import datetime
import os
import discord
from discord.ext import commands
from discord.ext.commands import has_permissions
import json

message_logs_path = 'message logs/'
today = datetime.datetime.today().day
if not os.path.exists(message_logs_path):
    os.mkdir(message_logs_path)

message_logs = dict()


def open_logfile(guild: str, filename: str, mode='a'):
    if not isinstance(guild, str):
        guild = str(guild)
    if not os.path.exists(message_logs_path + guild + '\\' + filename):
        if not os.path.exists(message_logs_path + guild):
            os.mkdir(message_logs_path + guild)
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


def remove_logfiles(oldest: datetime):
    oldest = int(oldest.strftime('%y%m%d'))
    for root, dirs, files in os.walk(message_logs_path):
        for file in files:
            file_num = int(file.split('.')[0])
            if file_num < oldest:
                os.remove(root + '/' + file)


def new_day():
    global today
    if datetime.datetime.today().day != today:
        today = datetime.datetime.today().day
        # new log file time
        for guild in message_logs:
            message_logs[guild].close()
            now = datetime.datetime.utcnow()
            message_logs[guild] = open_logfile(guild, now.strftime('%y%m%d') + '.txt')
            remove_logfiles(now - datetime.timedelta(days=7))


def log_guilds(guilds):
    for guild in guilds:
        message_logs[guild.id] = open_logfile(guild.id, datetime.datetime.utcnow().strftime('%y%m%d') + '.txt')


def log_message(message, dm, old=None):
    t = datetime.datetime.utcnow().strftime(f'%y%m%d%H%M%S:{int(datetime.datetime.utcnow().timestamp())} - ')
    s2 = '' if old is None else '====EDIT====\n\t====OLD====\n\t\t'

    def message_str(m):
        s = f'\n\t{m.jump_url}\n'
        s += f'\tcontent: {m.content}'
        for embed in m.embeds:
            s += '\n\tembed = ' + json.dumps(embed.to_dict())
        for attachment in m.attachments:
            s += '\n\tattachment = ' + attachment.url
        return s

    if dm:
        if old:
            s2 += f'dm:{old.author}({old.author.id}):{message_str(old)}\n\t====NEW====\n\t\t'
        s = f'dm:{message.author}({message.author.id}):{message_str(message)}'
    else:
        if old:
            s2 += f'{old.guild.name}({old.guild.id}):{old.channel.name}({old.channel.id}):' + \
                  f'{old.author}({old.author.id}):{message_str(old)}\n\t====NEW====\n\t\t'
        s = f'{message.guild.name}({message.guild.id}):{message.channel.name}({message.channel.id}):' + \
            f'{message.author}({message.author.id}):{message_str(message)}'
        message_logs[message.guild.id].write(t + s2 + s + '\n')
        message_logs[message.guild.id].flush()
    print(t + s)


class Logging(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(pass_context=True)
    @has_permissions(ban_members=True, kick_members=True)
    async def getlogs(self, ctx, days: int = None):
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


def setup(bot):
    bot.add_cog(Logging(bot))
