# stuff relating to managing users on the server


class Users:
    def __init__(self, bot):
        self.bot = bot


def setup(bot):
    bot.add_cog(Users(bot))
