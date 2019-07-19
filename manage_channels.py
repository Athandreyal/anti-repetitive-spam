# stuff relating to managing channels on a server


class Channels:
    def __init__(self, bot):
        self.bot = bot


def setup(bot):
    bot.add_cog(Channels(bot))
